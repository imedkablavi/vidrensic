from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
import json
import os
import sqlite3
import uuid


SCHEMA_VERSION = 1
PRIVATE_FILE_MODE = 0o600
MAX_JOB_JSON_BYTES = 1024 * 1024
MAX_JOB_ERROR_BYTES = 64 * 1024
MAX_JOB_KIND_CHARS = 256
MAX_NEW_JOB_ID_CHARS = 128

# Backward-compatible names kept for callers/tests written against the first
# hardening revision. The enforcement itself is byte-based for JSON/error text.
MAX_JOB_JSON_CHARS = MAX_JOB_JSON_BYTES
MAX_JOB_ERROR_CHARS = MAX_JOB_ERROR_BYTES
MAX_JOB_ID_CHARS = MAX_NEW_JOB_ID_CHARS


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


FINAL_STATUSES = frozenset({JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED})


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    kind: str
    status: JobStatus
    created_utc: str
    updated_utc: str
    parameters: dict[str, Any]
    checkpoint: dict[str, Any]
    progress_current: int | None
    progress_total: int | None
    error: str | None

    @property
    def progress_fraction(self) -> float | None:
        if self.progress_current is None or self.progress_total in (None, 0):
            return None
        return min(1.0, max(0.0, self.progress_current / self.progress_total))


_SAFE_PROJECTION = f"""
    job_id,
    kind,
    status,
    created_utc,
    updated_utc,
    CASE WHEN length(CAST(parameters_json AS BLOB)) <= {MAX_JOB_JSON_BYTES}
         THEN parameters_json ELSE NULL END AS parameters_json,
    CASE WHEN length(CAST(checkpoint_json AS BLOB)) <= {MAX_JOB_JSON_BYTES}
         THEN checkpoint_json ELSE NULL END AS checkpoint_json,
    progress_current,
    progress_total,
    CASE WHEN error IS NULL OR length(CAST(error AS BLOB)) <= {MAX_JOB_ERROR_BYTES}
         THEN error ELSE NULL END AS error,
    length(CAST(parameters_json AS BLOB)) AS parameters_bytes,
    length(CAST(checkpoint_json AS BLOB)) AS checkpoint_bytes,
    CASE WHEN error IS NULL THEN 0 ELSE length(CAST(error AS BLOB)) END AS error_bytes
"""


class JobStore:
    """Crash-resistant SQLite store for resumable forensic jobs.

    SQLite stores orchestration metadata only. Evidence bytes and native media stay
    in normal case directories and retain their own hashes/provenance. State
    transitions use `BEGIN IMMEDIATE` and compare the previous status in the
    UPDATE so competing processes cannot both finalize the same stale state.

    Job JSON/error fields are explicitly byte-bounded. Reads use NUL-safe SQLite
    BLOB-length checks so a tampered oversized JSON/error field is not
    materialized into Python before the store rejects the row.

    New custom job identifiers are bounded, but lookup/update operations retain
    compatibility with longer identifiers persisted by the schema-v1
    implementation before that creation limit existed.
    """

    def __init__(self, path: Path):
        self.path = path.expanduser().resolve()
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

                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    progress_current INTEGER,
                    progress_total INTEGER,
                    error TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                CREATE INDEX IF NOT EXISTS idx_jobs_kind ON jobs(kind);
                """
            )
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            elif int(row["value"]) != SCHEMA_VERSION:
                raise ValueError(f"unsupported job database schema: {row['value']}")

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _utf8_size(value: str) -> int:
        return len(value.encode("utf-8"))

    @staticmethod
    def _json(value: dict[str, Any]) -> str:
        if not isinstance(value, dict):
            raise ValueError("job metadata must be an object")
        try:
            serialized = json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError("job metadata must be JSON-serializable") from exc
        if JobStore._utf8_size(serialized) > MAX_JOB_JSON_BYTES:
            raise ValueError(f"job metadata exceeds {MAX_JOB_JSON_BYTES} bytes")
        return serialized

    @staticmethod
    def _parse_json_object(value: str | None, *, field: str, stored_bytes: int) -> dict[str, Any]:
        if stored_bytes > MAX_JOB_JSON_BYTES or value is None:
            raise ValueError(f"stored job {field} exceeds {MAX_JOB_JSON_BYTES} bytes")
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise ValueError(f"stored job {field} is invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"stored job {field} must be a JSON object")
        return parsed

    @staticmethod
    def _validate_progress(current: int | None, total: int | None) -> None:
        if current is not None and current < 0:
            raise ValueError("progress_current cannot be negative")
        if total is not None and total < 0:
            raise ValueError("progress_total cannot be negative")
        if current is not None and total is not None and current > total:
            raise ValueError("progress_current cannot exceed progress_total")

    @staticmethod
    def _validate_kind(kind: str) -> None:
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("job kind cannot be empty")
        if len(kind) > MAX_JOB_KIND_CHARS:
            raise ValueError(f"job kind exceeds {MAX_JOB_KIND_CHARS} characters")

    @staticmethod
    def _validate_lookup_identifier(identifier: str) -> None:
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("job_id must be a non-empty string")

    @staticmethod
    def _validate_new_identifier(identifier: str) -> None:
        JobStore._validate_lookup_identifier(identifier)
        if len(identifier) > MAX_NEW_JOB_ID_CHARS:
            raise ValueError(f"job_id exceeds {MAX_NEW_JOB_ID_CHARS} characters")

    @staticmethod
    def _safe_row(conn: sqlite3.Connection, job_id: str) -> sqlite3.Row | None:
        return conn.execute(
            f"SELECT {_SAFE_PROJECTION} FROM jobs WHERE job_id=?",
            (job_id,),
        ).fetchone()

    def create(
        self,
        kind: str,
        parameters: dict[str, Any],
        *,
        checkpoint: dict[str, Any] | None = None,
        job_id: str | None = None,
    ) -> JobRecord:
        self._validate_kind(kind)
        identifier = job_id or str(uuid.uuid4())
        self._validate_new_identifier(identifier)
        parameters_json = self._json(parameters)
        checkpoint_json = self._json(checkpoint or {})
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs(
                    job_id, kind, status, created_utc, updated_utc,
                    parameters_json, checkpoint_json, progress_current,
                    progress_total, error
                ) VALUES(?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
                """,
                (
                    identifier,
                    kind,
                    JobStatus.PENDING.value,
                    now,
                    now,
                    parameters_json,
                    checkpoint_json,
                ),
            )
        return self.get(identifier)

    def get(self, job_id: str) -> JobRecord:
        self._validate_lookup_identifier(job_id)
        with self._connect() as conn:
            row = self._safe_row(conn, job_id)
        if row is None:
            raise KeyError(f"unknown job: {job_id}")
        return self._from_row(row)

    def list(
        self,
        *,
        status: JobStatus | None = None,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[JobRecord]:
        if limit <= 0 or limit > 10000:
            raise ValueError("limit must be between 1 and 10000")
        clauses: list[str] = []
        values: list[Any] = []
        if status is not None:
            clauses.append("status=?")
            values.append(status.value)
        if kind is not None:
            self._validate_kind(kind)
            clauses.append("kind=?")
            values.append(kind)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT {_SAFE_PROJECTION} FROM jobs{where} ORDER BY created_utc DESC LIMIT ?"
        values.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, values).fetchall()
        return [self._from_row(row) for row in rows]

    def start(self, job_id: str) -> JobRecord:
        return self._set_status(job_id, JobStatus.RUNNING)

    def pause(self, job_id: str) -> JobRecord:
        return self._set_status(job_id, JobStatus.PAUSED)

    def complete(self, job_id: str) -> JobRecord:
        return self._set_status(job_id, JobStatus.COMPLETED)

    def cancel(self, job_id: str) -> JobRecord:
        return self._set_status(job_id, JobStatus.CANCELLED)

    def fail(self, job_id: str, error: str) -> JobRecord:
        if not isinstance(error, str) or not error:
            raise ValueError("error cannot be empty")
        if self._utf8_size(error) > MAX_JOB_ERROR_BYTES:
            raise ValueError(f"job error exceeds {MAX_JOB_ERROR_BYTES} bytes")
        return self._set_status(job_id, JobStatus.FAILED, error=error)

    def _set_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
    ) -> JobRecord:
        self._validate_lookup_identifier(job_id)
        if error is not None and self._utf8_size(error) > MAX_JOB_ERROR_BYTES:
            raise ValueError(f"job error exceeds {MAX_JOB_ERROR_BYTES} bytes")
        allowed = {
            JobStatus.PENDING: {JobStatus.RUNNING, JobStatus.CANCELLED, JobStatus.FAILED},
            JobStatus.RUNNING: {
                JobStatus.PAUSED,
                JobStatus.COMPLETED,
                JobStatus.CANCELLED,
                JobStatus.FAILED,
            },
            JobStatus.PAUSED: {JobStatus.RUNNING, JobStatus.CANCELLED, JobStatus.FAILED},
        }
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._safe_row(conn, job_id)
            if row is None:
                raise KeyError(f"unknown job: {job_id}")
            existing = self._from_row(row)
            if existing.status in FINAL_STATUSES:
                raise ValueError(f"job is already final: {existing.status.value}")
            if status not in allowed.get(existing.status, set()):
                raise ValueError(f"invalid job transition {existing.status.value} -> {status.value}")
            cursor = conn.execute(
                """
                UPDATE jobs SET status=?, updated_utc=?, error=?
                WHERE job_id=? AND status=?
                """,
                (status.value, self._now(), error, job_id, existing.status.value),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("job status changed concurrently; retry from fresh state")
        return self.get(job_id)

    def checkpoint(
        self,
        job_id: str,
        value: dict[str, Any],
        *,
        progress_current: int | None = None,
        progress_total: int | None = None,
    ) -> JobRecord:
        self._validate_lookup_identifier(job_id)
        checkpoint_json = self._json(value)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._safe_row(conn, job_id)
            if row is None:
                raise KeyError(f"unknown job: {job_id}")
            existing = self._from_row(row)
            if existing.status in FINAL_STATUSES:
                raise ValueError("cannot checkpoint a final job")
            current = existing.progress_current if progress_current is None else progress_current
            total = existing.progress_total if progress_total is None else progress_total
            self._validate_progress(current, total)
            cursor = conn.execute(
                """
                UPDATE jobs
                SET checkpoint_json=?, progress_current=?, progress_total=?, updated_utc=?
                WHERE job_id=? AND status=?
                """,
                (
                    checkpoint_json,
                    current,
                    total,
                    self._now(),
                    job_id,
                    existing.status.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("job status changed concurrently; checkpoint was not committed")
        return self.get(job_id)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> JobRecord:
        parameters = JobStore._parse_json_object(
            row["parameters_json"],
            field="parameters",
            stored_bytes=int(row["parameters_bytes"]),
        )
        checkpoint = JobStore._parse_json_object(
            row["checkpoint_json"],
            field="checkpoint",
            stored_bytes=int(row["checkpoint_bytes"]),
        )
        error_bytes = int(row["error_bytes"])
        if error_bytes > MAX_JOB_ERROR_BYTES:
            raise ValueError(f"stored job error exceeds {MAX_JOB_ERROR_BYTES} bytes")
        return JobRecord(
            job_id=row["job_id"],
            kind=row["kind"],
            status=JobStatus(row["status"]),
            created_utc=row["created_utc"],
            updated_utc=row["updated_utc"],
            parameters=parameters,
            checkpoint=checkpoint,
            progress_current=row["progress_current"],
            progress_total=row["progress_total"],
            error=row["error"],
        )
