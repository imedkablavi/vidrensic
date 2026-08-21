from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
import json
import sqlite3
import uuid


SCHEMA_VERSION = 1


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


class JobStore:
    """Crash-resistant SQLite store for resumable forensic jobs.

    SQLite stores orchestration metadata only. Evidence bytes and native media stay
    in normal case directories and retain their own hashes/provenance. State
    transitions use `BEGIN IMMEDIATE` and compare the previous status in the
    UPDATE so competing processes cannot both finalize the same stale state.
    """

    def __init__(self, path: Path):
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

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
    def _json(value: dict[str, Any]) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _validate_progress(current: int | None, total: int | None) -> None:
        if current is not None and current < 0:
            raise ValueError("progress_current cannot be negative")
        if total is not None and total < 0:
            raise ValueError("progress_total cannot be negative")
        if current is not None and total is not None and current > total:
            raise ValueError("progress_current cannot exceed progress_total")

    def create(
        self,
        kind: str,
        parameters: dict[str, Any],
        *,
        checkpoint: dict[str, Any] | None = None,
        job_id: str | None = None,
    ) -> JobRecord:
        if not kind.strip():
            raise ValueError("job kind cannot be empty")
        identifier = job_id or str(uuid.uuid4())
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
                    self._json(parameters),
                    self._json(checkpoint or {}),
                ),
            )
        return self.get(identifier)

    def get(self, job_id: str) -> JobRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
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
            clauses.append("kind=?")
            values.append(kind)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM jobs{where} ORDER BY created_utc DESC LIMIT ?"
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
        if not error:
            raise ValueError("error cannot be empty")
        return self._set_status(job_id, JobStatus.FAILED, error=error)

    def _set_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
    ) -> JobRecord:
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
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
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
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
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
                    self._json(value),
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
        return JobRecord(
            job_id=row["job_id"],
            kind=row["kind"],
            status=JobStatus(row["status"]),
            created_utc=row["created_utc"],
            updated_utc=row["updated_utc"],
            parameters=json.loads(row["parameters_json"]),
            checkpoint=json.loads(row["checkpoint_json"]),
            progress_current=row["progress_current"],
            progress_total=row["progress_total"],
            error=row["error"],
        )
