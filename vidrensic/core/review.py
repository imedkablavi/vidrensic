from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
import os
import sqlite3
import uuid

from vidrensic.core.audit import AuditLog


SCHEMA_VERSION = 1
PRIVATE_FILE_MODE = 0o600
MAX_NOTE_CHARS = 16 * 1024
MAX_LABEL_CHARS = 512
MAX_ITEMS = 10000
MAX_BOOKMARKS = 10000


class ReviewState(StrEnum):
    REVIEW = "REVIEW"
    KEEP = "KEEP"
    DISCARD = "DISCARD"


@dataclass(frozen=True)
class ReviewItem:
    item_id: str
    artifact: Path
    artifact_sha256: str
    kind: str
    duration_seconds: float | None
    state: ReviewState
    note: str
    created_utc: str
    updated_utc: str


@dataclass(frozen=True)
class ReviewBookmark:
    bookmark_id: str
    item_id: str
    timestamp_seconds: float
    label: str
    note: str
    created_utc: str


class ReviewStore:
    """Auditable analyst review state separate from evidence bytes."""

    def __init__(
        self,
        path: Path,
        *,
        case_root: Path,
        audit: AuditLog | None = None,
        actor: str | None = None,
    ):
        self.path = path.expanduser().resolve()
        self.case_root = case_root.expanduser().resolve()
        self.audit = audit
        self.actor = actor
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        os.chmod(self.path, PRIVATE_FILE_MODE)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = FULL")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS items (
                    item_id TEXT PRIMARY KEY,
                    artifact_path TEXT NOT NULL,
                    artifact_sha256 TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    duration_seconds REAL,
                    state TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL,
                    UNIQUE(artifact_path, artifact_sha256)
                );

                CREATE TABLE IF NOT EXISTS bookmarks (
                    bookmark_id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
                    timestamp_seconds REAL NOT NULL,
                    label TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_utc TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_review_items_state ON items(state);
                CREATE INDEX IF NOT EXISTS idx_review_bookmarks_item ON bookmarks(item_id);
                """
            )
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            elif int(row["value"]) != SCHEMA_VERSION:
                raise ValueError(f"unsupported review database schema: {row['value']}")

    def _artifact(self, artifact: Path) -> Path:
        candidate = artifact.expanduser()
        if candidate.is_symlink():
            raise ValueError("review artifact may not be a symlink")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_file():
            raise ValueError("review artifact must be a regular file")
        try:
            resolved.relative_to(self.case_root)
        except ValueError as exc:
            raise ValueError("review artifact must be inside the case root") from exc
        return resolved

    @staticmethod
    def _validate_sha256(value: str) -> None:
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError("artifact_sha256 must be a 64-character hex digest")
        try:
            int(value, 16)
        except ValueError as exc:
            raise ValueError("artifact_sha256 must be hexadecimal") from exc

    @staticmethod
    def _validate_text(value: str, *, field: str, limit: int) -> None:
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a string")
        if len(value) > limit:
            raise ValueError(f"{field} exceeds {limit} characters")

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def register_item(
        self,
        artifact: Path,
        artifact_sha256: str,
        *,
        kind: str = "media",
        duration_seconds: float | None = None,
        state: ReviewState = ReviewState.REVIEW,
        note: str = "",
    ) -> ReviewItem:
        path = self._artifact(artifact)
        self._validate_sha256(artifact_sha256)
        self._validate_text(kind, field="kind", limit=MAX_LABEL_CHARS)
        self._validate_text(note, field="note", limit=MAX_NOTE_CHARS)
        if duration_seconds is not None and (duration_seconds < 0 or not float(duration_seconds) == duration_seconds):
            raise ValueError("duration_seconds must be a finite non-negative number")
        now = self._now()
        item_id = str(uuid.uuid4())
        with self._connect() as conn:
            row = conn.execute(
                "SELECT item_id FROM items WHERE artifact_path=? AND artifact_sha256=?",
                (str(path), artifact_sha256.lower()),
            ).fetchone()
            if row:
                return self.get_item(str(row["item_id"]))
            conn.execute(
                """
                INSERT INTO items(
                    item_id, artifact_path, artifact_sha256, kind, duration_seconds,
                    state, note, created_utc, updated_utc
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    str(path),
                    artifact_sha256.lower(),
                    kind,
                    duration_seconds,
                    state.value,
                    note,
                    now,
                    now,
                ),
            )
        item = self.get_item(item_id)
        self._audit(
            "review.item.registered",
            {
                "item_id": item.item_id,
                "artifact": str(item.artifact),
                "artifact_sha256": item.artifact_sha256,
                "kind": item.kind,
            },
        )
        return item

    def get_item(self, item_id: str) -> ReviewItem:
        if not item_id:
            raise ValueError("item_id cannot be empty")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown review item: {item_id}")
        return self._item(row)

    def list_items(self, *, state: ReviewState | None = None, limit: int = 1000) -> list[ReviewItem]:
        if not 1 <= limit <= MAX_ITEMS:
            raise ValueError(f"limit must be between 1 and {MAX_ITEMS}")
        if state is None:
            query = "SELECT * FROM items ORDER BY updated_utc DESC LIMIT ?"
            values = (limit,)
        else:
            query = "SELECT * FROM items WHERE state=? ORDER BY updated_utc DESC LIMIT ?"
            values = (state.value, limit)
        with self._connect() as conn:
            rows = conn.execute(query, values).fetchall()
        return [self._item(row) for row in rows]

    def set_state(self, item_id: str, *, state: ReviewState, expected_sha256: str) -> ReviewItem:
        self._validate_sha256(expected_sha256)
        current = self.get_item(item_id)
        if current.artifact_sha256 != expected_sha256.lower():
            raise ValueError("artifact SHA-256 does not match registered review item")
        now = self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE items SET state=?, updated_utc=? WHERE item_id=? AND artifact_sha256=?",
                (state.value, now, item_id, expected_sha256.lower()),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("review item changed concurrently; retry from fresh state")
        item = self.get_item(item_id)
        self._audit(
            "review.item.state_changed",
            {
                "item_id": item_id,
                "artifact_sha256": expected_sha256.lower(),
                "state": state.value,
            },
        )
        return item

    def set_note(self, item_id: str, *, note: str, expected_sha256: str) -> ReviewItem:
        self._validate_text(note, field="note", limit=MAX_NOTE_CHARS)
        self._validate_sha256(expected_sha256)
        current = self.get_item(item_id)
        if current.artifact_sha256 != expected_sha256.lower():
            raise ValueError("artifact SHA-256 does not match registered review item")
        now = self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE items SET note=?, updated_utc=? WHERE item_id=? AND artifact_sha256=?",
                (note, now, item_id, expected_sha256.lower()),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("review item changed concurrently; retry from fresh state")
        item = self.get_item(item_id)
        self._audit(
            "review.item.note_changed",
            {"item_id": item_id, "artifact_sha256": expected_sha256.lower()},
        )
        return item

    def add_bookmark(
        self,
        item_id: str,
        *,
        timestamp_seconds: float,
        expected_sha256: str,
        label: str = "",
        note: str = "",
    ) -> ReviewBookmark:
        self._validate_sha256(expected_sha256)
        self._validate_text(label, field="label", limit=MAX_LABEL_CHARS)
        self._validate_text(note, field="note", limit=MAX_NOTE_CHARS)
        if timestamp_seconds < 0 or not float(timestamp_seconds) == timestamp_seconds:
            raise ValueError("timestamp_seconds must be a finite non-negative number")
        item = self.get_item(item_id)
        if item.artifact_sha256 != expected_sha256.lower():
            raise ValueError("artifact SHA-256 does not match registered review item")
        if item.duration_seconds is not None and timestamp_seconds > item.duration_seconds:
            raise ValueError("bookmark timestamp exceeds registered media duration")
        bookmark_id = str(uuid.uuid4())
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO bookmarks(
                    bookmark_id, item_id, timestamp_seconds, label, note, created_utc
                ) VALUES(?, ?, ?, ?, ?, ?)
                """,
                (bookmark_id, item_id, timestamp_seconds, label, note, now),
            )
        bookmark = self.get_bookmark(bookmark_id)
        self._audit(
            "review.bookmark.created",
            {
                "bookmark_id": bookmark.bookmark_id,
                "item_id": bookmark.item_id,
                "artifact_sha256": expected_sha256.lower(),
                "timestamp_seconds": bookmark.timestamp_seconds,
            },
        )
        return bookmark

    def get_bookmark(self, bookmark_id: str) -> ReviewBookmark:
        if not bookmark_id:
            raise ValueError("bookmark_id cannot be empty")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM bookmarks WHERE bookmark_id=?",
                (bookmark_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown bookmark: {bookmark_id}")
        return self._bookmark(row)

    def list_bookmarks(self, item_id: str, *, limit: int = 1000) -> list[ReviewBookmark]:
        if not 1 <= limit <= MAX_BOOKMARKS:
            raise ValueError(f"limit must be between 1 and {MAX_BOOKMARKS}")
        self.get_item(item_id)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM bookmarks WHERE item_id=? ORDER BY timestamp_seconds ASC LIMIT ?",
                (item_id, limit),
            ).fetchall()
        return [self._bookmark(row) for row in rows]

    def _audit(self, event: str, details: dict) -> None:
        if self.audit is not None:
            self.audit.append(event, details, actor=self.actor)

    @staticmethod
    def _item(row: sqlite3.Row) -> ReviewItem:
        return ReviewItem(
            item_id=str(row["item_id"]),
            artifact=Path(row["artifact_path"]),
            artifact_sha256=str(row["artifact_sha256"]),
            kind=str(row["kind"]),
            duration_seconds=row["duration_seconds"],
            state=ReviewState(row["state"]),
            note=str(row["note"]),
            created_utc=str(row["created_utc"]),
            updated_utc=str(row["updated_utc"]),
        )

    @staticmethod
    def _bookmark(row: sqlite3.Row) -> ReviewBookmark:
        return ReviewBookmark(
            bookmark_id=str(row["bookmark_id"]),
            item_id=str(row["item_id"]),
            timestamp_seconds=float(row["timestamp_seconds"]),
            label=str(row["label"]),
            note=str(row["note"]),
            created_utc=str(row["created_utc"]),
        )
