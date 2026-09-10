from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import json
import math
import os
import sqlite3
import uuid

from vidrensic.core.audit import AuditLog
from vidrensic.core.hashing import forensic_hashes_stable


SCHEMA_VERSION = 1
PRIVATE_FILE_MODE = 0o600
MAX_CLAIMS = 16
MAX_TEXT_CHARS = 1024
MAX_POINTER_CHARS = 2048
MAX_SOURCE_KIND_CHARS = 128
MAX_RECORDING_YEAR = 9999

ALLOWED_FIELDS = {
    "recording_start_utc",
    "recording_end_utc",
    "camera_slot",
    "source_label",
    "format_family",
}
ALLOWED_SOURCE_KINDS = {
    "native-metadata",
    "timeline-report",
    "reconstruction-manifest",
    "operator-observation",
}


class CandidateMetadataError(ValueError):
    """Raised when candidate metadata cannot be safely persisted."""


@dataclass(frozen=True)
class MetadataClaim:
    claim_id: str
    item_id: str
    artifact_sha256: str
    field: str
    value: str
    source_kind: str
    source_path: Path | None
    source_sha256: str | None
    evidence_pointer: str | None
    confidence: float
    created_utc: str

    def to_dict(self) -> dict[str, object]:
        return {
            "claim_id": self.claim_id,
            "item_id": self.item_id,
            "artifact_sha256": self.artifact_sha256,
            "field": self.field,
            "value": self.value,
            "source_kind": self.source_kind,
            "source_path": None if self.source_path is None else str(self.source_path),
            "source_sha256": self.source_sha256,
            "evidence_pointer": self.evidence_pointer,
            "confidence": self.confidence,
            "created_utc": self.created_utc,
        }


@dataclass(frozen=True)
class CandidateMetadata:
    item_id: str
    artifact_sha256: str
    claims: tuple[MetadataClaim, ...]

    def values(self) -> dict[str, str]:
        return {claim.field: claim.value for claim in self.claims}

    def to_dict(self) -> dict[str, object]:
        values = self.values()
        return {
            "item_id": self.item_id,
            "artifact_sha256": self.artifact_sha256,
            "recording_start_utc": values.get("recording_start_utc"),
            "recording_end_utc": values.get("recording_end_utc"),
            "camera_slot": values.get("camera_slot"),
            "source_label": values.get("source_label"),
            "format_family": values.get("format_family"),
            "claims": [claim.to_dict() for claim in self.claims],
            "evidence_backed": all(
                claim.source_sha256 is not None for claim in self.claims
            ),
        }


class CandidateMetadataStore:
    """Persist candidate metadata separately from analyst review state."""

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
        original = path.expanduser()
        if original.is_symlink():
            raise CandidateMetadataError("candidate metadata database may not be a symlink")
        try:
            self.path.relative_to(self.case_root)
        except ValueError as exc:
            raise CandidateMetadataError("candidate metadata database must be inside the case") from exc
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

                CREATE TABLE IF NOT EXISTS claims (
                    claim_id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL,
                    artifact_sha256 TEXT NOT NULL,
                    field TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_path TEXT,
                    source_sha256 TEXT,
                    evidence_pointer TEXT,
                    confidence REAL NOT NULL,
                    created_utc TEXT NOT NULL,
                    UNIQUE(item_id, field, value, artifact_sha256, source_sha256)
                );

                CREATE INDEX IF NOT EXISTS idx_metadata_item ON claims(item_id);
                CREATE INDEX IF NOT EXISTS idx_metadata_field ON claims(field);
                CREATE INDEX IF NOT EXISTS idx_metadata_recording_start
                    ON claims(field, value);
                """
            )
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            elif int(row["value"]) != SCHEMA_VERSION:
                raise CandidateMetadataError(
                    f"unsupported candidate metadata schema: {row['value']}"
                )

    @staticmethod
    def _validate_sha256(value: str, *, field: str) -> str:
        if not isinstance(value, str) or len(value) != 64:
            raise CandidateMetadataError(f"{field} must be a 64-character hex digest")
        try:
            int(value, 16)
        except ValueError as exc:
            raise CandidateMetadataError(f"{field} must be hexadecimal") from exc
        return value.lower()

    @staticmethod
    def _validate_text(value: str, *, field: str, limit: int = MAX_TEXT_CHARS) -> str:
        if not isinstance(value, str) or not value.strip():
            raise CandidateMetadataError(f"{field} must be a non-empty string")
        value = value.strip()
        if len(value) > limit:
            raise CandidateMetadataError(f"{field} exceeds {limit} characters")
        return value

    @staticmethod
    def _validate_confidence(value: float | int) -> float:
        if isinstance(value, bool):
            raise CandidateMetadataError("confidence must be a finite number between 0 and 1")
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise CandidateMetadataError("confidence must be a finite number between 0 and 1") from exc
        if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
            raise CandidateMetadataError("confidence must be a finite number between 0 and 1")
        return numeric

    @staticmethod
    def _validate_timestamp(value: str, *, field: str) -> str:
        value = CandidateMetadataStore._validate_text(value, field=field)
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CandidateMetadataError(f"{field} must be ISO-8601") from exc
        if parsed.tzinfo is None:
            raise CandidateMetadataError(f"{field} must include a timezone")
        return value

    def _source(self, source_path: Path | None, source_sha256: str | None) -> tuple[Path | None, str | None]:
        if source_path is None:
            if source_sha256 is not None:
                raise CandidateMetadataError("source_sha256 requires source_path")
            return None, None
        candidate = source_path.expanduser()
        if candidate.is_symlink():
            raise CandidateMetadataError("metadata source file may not be a symlink")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_file():
            raise CandidateMetadataError("metadata source must be a regular file")
        try:
            resolved.relative_to(self.case_root)
        except ValueError as exc:
            raise CandidateMetadataError("metadata source must be inside the case") from exc
        digest = forensic_hashes_stable(resolved).sha256
        if source_sha256 is not None and digest != self._validate_sha256(source_sha256, field="source_sha256"):
            raise CandidateMetadataError("metadata source SHA-256 does not match the file")
        return resolved, digest

    def _validate_claim(
        self,
        *,
        field: str,
        value: str,
        source_kind: str,
        source_path: Path | None,
        source_sha256: str | None,
        evidence_pointer: str | None,
        confidence: float | int,
    ) -> tuple[str, str, Path | None, str | None, str | None, float]:
        if field not in ALLOWED_FIELDS:
            raise CandidateMetadataError(f"unsupported metadata field: {field!r}")
        if source_kind not in ALLOWED_SOURCE_KINDS:
            raise CandidateMetadataError(f"unsupported metadata source kind: {source_kind!r}")
        if field.endswith("_utc"):
            normalized_value = self._validate_timestamp(value, field=field)
        else:
            normalized_value = self._validate_text(value, field=field)
        normalized_source_kind = self._validate_text(
            source_kind,
            field="source_kind",
            limit=MAX_SOURCE_KIND_CHARS,
        )
        resolved_source, observed_source_sha256 = self._source(source_path, source_sha256)
        if normalized_source_kind != "operator-observation" and resolved_source is None:
            raise CandidateMetadataError(
                "evidence-backed metadata requires source_path for non-operator source kinds"
            )
        pointer = None
        if evidence_pointer is not None:
            pointer = self._validate_text(
                evidence_pointer,
                field="evidence_pointer",
                limit=MAX_POINTER_CHARS,
            )
        return (
            normalized_value,
            normalized_source_kind,
            resolved_source,
            observed_source_sha256,
            pointer,
            self._validate_confidence(confidence),
        )

    def set_claim(
        self,
        item_id: str,
        artifact_sha256: str,
        *,
        field: str,
        value: str,
        source_kind: str,
        source_path: Path | None = None,
        source_sha256: str | None = None,
        evidence_pointer: str | None = None,
        confidence: float = 1.0,
    ) -> MetadataClaim:
        sha = self._validate_sha256(artifact_sha256, field="artifact_sha256")
        normalized = self._validate_claim(
            field=field,
            value=value,
            source_kind=source_kind,
            source_path=source_path,
            source_sha256=source_sha256,
            evidence_pointer=evidence_pointer,
            confidence=confidence,
        )
        now = datetime.now(UTC).isoformat()
        claim = MetadataClaim(
            claim_id=str(uuid.uuid4()),
            item_id=item_id,
            artifact_sha256=sha,
            field=field,
            value=normalized[0],
            source_kind=normalized[1],
            source_path=normalized[2],
            source_sha256=normalized[3],
            evidence_pointer=normalized[4],
            confidence=normalized[5],
            created_utc=now,
        )
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM claims WHERE item_id=? AND artifact_sha256=?",
                (item_id, sha),
            ).fetchone()["count"]
            if int(count) >= MAX_CLAIMS:
                raise CandidateMetadataError(f"metadata claim limit of {MAX_CLAIMS} reached")
            conn.execute(
                """
                INSERT OR REPLACE INTO claims(
                    claim_id, item_id, artifact_sha256, field, value, source_kind,
                    source_path, source_sha256, evidence_pointer, confidence, created_utc
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim.claim_id,
                    claim.item_id,
                    claim.artifact_sha256,
                    claim.field,
                    claim.value,
                    claim.source_kind,
                    None if claim.source_path is None else str(claim.source_path),
                    claim.source_sha256,
                    claim.evidence_pointer,
                    claim.confidence,
                    claim.created_utc,
                ),
            )
        if self.audit is not None:
            self.audit.append(
                "review.candidate-metadata.claim-set",
                {
                    "item_id": item_id,
                    "artifact_sha256": sha,
                    "field": field,
                    "source_kind": claim.source_kind,
                    "source": None if claim.source_path is None else str(claim.source_path),
                    "source_sha256": claim.source_sha256,
                    "confidence": claim.confidence,
                },
                actor=self.actor,
            )
        return claim

    def list_claims(self, item_id: str, *, artifact_sha256: str | None = None) -> list[MetadataClaim]:
        params: tuple[object, ...]
        if artifact_sha256 is None:
            query = "SELECT * FROM claims WHERE item_id=? ORDER BY created_utc, claim_id"
            params = (item_id,)
        else:
            sha = self._validate_sha256(artifact_sha256, field="artifact_sha256")
            query = "SELECT * FROM claims WHERE item_id=? AND artifact_sha256=? ORDER BY created_utc, claim_id"
            params = (item_id, sha)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._claim(row) for row in rows]

    def get(self, item_id: str, artifact_sha256: str) -> CandidateMetadata:
        sha = self._validate_sha256(artifact_sha256, field="artifact_sha256")
        claims = tuple(self.list_claims(item_id, artifact_sha256=sha))
        return CandidateMetadata(item_id=item_id, artifact_sha256=sha, claims=claims)

    def remove_claim(self, claim_id: str, item_id: str, artifact_sha256: str) -> None:
        sha = self._validate_sha256(artifact_sha256, field="artifact_sha256")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "DELETE FROM claims WHERE claim_id=? AND item_id=? AND artifact_sha256=?",
                (claim_id, item_id, sha),
            )
            if cursor.rowcount != 1:
                raise KeyError("metadata claim not found")
        if self.audit is not None:
            self.audit.append(
                "review.candidate-metadata.claim-removed",
                {"claim_id": claim_id, "item_id": item_id, "artifact_sha256": sha},
                actor=self.actor,
            )

    @staticmethod
    def _claim(row: sqlite3.Row) -> MetadataClaim:
        return MetadataClaim(
            claim_id=str(row["claim_id"]),
            item_id=str(row["item_id"]),
            artifact_sha256=str(row["artifact_sha256"]),
            field=str(row["field"]),
            value=str(row["value"]),
            source_kind=str(row["source_kind"]),
            source_path=None if row["source_path"] is None else Path(str(row["source_path"])),
            source_sha256=None if row["source_sha256"] is None else str(row["source_sha256"]),
            evidence_pointer=None if row["evidence_pointer"] is None else str(row["evidence_pointer"]),
            confidence=float(row["confidence"]),
            created_utc=str(row["created_utc"]),
        )
