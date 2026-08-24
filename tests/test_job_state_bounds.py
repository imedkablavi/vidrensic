from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from vidrensic.core.jobs import (
    MAX_JOB_ERROR_BYTES,
    MAX_NEW_JOB_ID_CHARS,
    MAX_JOB_JSON_BYTES,
    MAX_JOB_KIND_CHARS,
    JobStatus,
    JobStore,
)


def _store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / "jobs.sqlite3")


def test_job_create_rejects_oversized_kind_id_and_metadata(tmp_path: Path) -> None:
    jobs = _store(tmp_path)
    with pytest.raises(ValueError, match="job kind exceeds"):
        jobs.create("K" * (MAX_JOB_KIND_CHARS + 1), {})
    with pytest.raises(ValueError, match="job_id exceeds"):
        jobs.create("scan", {}, job_id="J" * (MAX_NEW_JOB_ID_CHARS + 1))
    with pytest.raises(ValueError, match="job metadata exceeds"):
        jobs.create("scan", {"blob": "X" * (MAX_JOB_JSON_BYTES + 1)})


def test_job_checkpoint_and_error_are_bounded_before_database_write(tmp_path: Path) -> None:
    jobs = _store(tmp_path)
    job = jobs.create("scan", {})
    job = jobs.start(job.job_id)

    with pytest.raises(ValueError, match="job metadata exceeds"):
        jobs.checkpoint(job.job_id, {"blob": "X" * (MAX_JOB_JSON_BYTES + 1)})
    with pytest.raises(ValueError, match="job error exceeds"):
        jobs.fail(job.job_id, "E" * (MAX_JOB_ERROR_BYTES + 1))

    fresh = jobs.get(job.job_id)
    assert fresh.checkpoint == {}
    assert fresh.error is None


def test_write_bounds_count_utf8_bytes_not_python_characters(tmp_path: Path) -> None:
    jobs = _store(tmp_path)
    # Two-byte UTF-8 characters must count by stored bytes, not code points.
    with pytest.raises(ValueError, match="job metadata exceeds"):
        jobs.create("scan", {"blob": "é" * (MAX_JOB_JSON_BYTES // 2 + 64)})

    job = jobs.create("scan", {})
    job = jobs.start(job.job_id)
    with pytest.raises(ValueError, match="job error exceeds"):
        jobs.fail(job.job_id, "é" * (MAX_JOB_ERROR_BYTES // 2 + 1))


def test_safe_read_rejects_tampered_oversized_json_without_returning_text(
    tmp_path: Path,
) -> None:
    jobs = _store(tmp_path)
    job = jobs.create("scan", {"safe": True})

    with sqlite3.connect(jobs.path) as conn:
        conn.execute(
            "UPDATE jobs SET parameters_json=? WHERE job_id=?",
            ('{"blob":"' + ("X" * (MAX_JOB_JSON_BYTES + 1)) + '"}', job.job_id),
        )

    with pytest.raises(ValueError, match="stored job parameters exceeds"):
        jobs.get(job.job_id)
    with pytest.raises(ValueError, match="stored job parameters exceeds"):
        jobs.list()


def test_safe_read_uses_nul_safe_blob_length_for_tampered_fields(tmp_path: Path) -> None:
    jobs = _store(tmp_path)
    job = jobs.create("scan", {})

    oversized_error = "ok\x00" + ("E" * (MAX_JOB_ERROR_BYTES + 1))
    with sqlite3.connect(jobs.path) as conn:
        conn.execute(
            "UPDATE jobs SET error=? WHERE job_id=?",
            (oversized_error, job.job_id),
        )
    with pytest.raises(ValueError, match="stored job error exceeds"):
        jobs.get(job.job_id)

    # JSON permits U+0000 when escaped. Store a valid JSON document whose
    # decoded SQLite TEXT contains an actual NUL before a suffix that makes the
    # raw stored value exceed the configured byte bound.
    oversized_json = '{"prefix":"x\u0000","blob":"' + ("Z" * (MAX_JOB_JSON_BYTES + 1)) + '"}'
    with sqlite3.connect(jobs.path) as conn:
        conn.execute(
            "UPDATE jobs SET parameters_json=? WHERE job_id=?",
            (oversized_json, job.job_id),
        )
    with pytest.raises(ValueError, match="stored job parameters exceeds"):
        jobs.get(job.job_id)


def test_safe_read_rejects_malformed_or_non_object_job_json(tmp_path: Path) -> None:
    jobs = _store(tmp_path)
    job = jobs.create("scan", {})

    with sqlite3.connect(jobs.path) as conn:
        conn.execute(
            "UPDATE jobs SET checkpoint_json=? WHERE job_id=?",
            ("not-json", job.job_id),
        )
    with pytest.raises(ValueError, match="checkpoint is invalid JSON"):
        jobs.get(job.job_id)

    with sqlite3.connect(jobs.path) as conn:
        conn.execute(
            "UPDATE jobs SET checkpoint_json=? WHERE job_id=?",
            ("[]", job.job_id),
        )
    with pytest.raises(ValueError, match="checkpoint must be a JSON object"):
        jobs.get(job.job_id)


def test_safe_read_rejects_tampered_oversized_error(tmp_path: Path) -> None:
    jobs = _store(tmp_path)
    job = jobs.create("scan", {})

    with sqlite3.connect(jobs.path) as conn:
        conn.execute(
            "UPDATE jobs SET error=? WHERE job_id=?",
            ("E" * (MAX_JOB_ERROR_BYTES + 1), job.job_id),
        )
    with pytest.raises(ValueError, match="stored job error exceeds"):
        jobs.get(job.job_id)


def test_legacy_long_job_id_remains_accessible_and_resumable(tmp_path: Path) -> None:
    jobs = _store(tmp_path)
    legacy_id = "legacy-" + ("L" * (MAX_NEW_JOB_ID_CHARS + 256))
    now = jobs._now()

    # Simulate a schema-v1 database created before the new-ID creation bound.
    with sqlite3.connect(jobs.path) as conn:
        conn.execute(
            """
            INSERT INTO jobs(
                job_id, kind, status, created_utc, updated_utc,
                parameters_json, checkpoint_json, progress_current,
                progress_total, error
            ) VALUES(?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
            """,
            (legacy_id, "legacy.scan", JobStatus.PENDING.value, now, now, "{}", "{}"),
        )

    loaded = jobs.get(legacy_id)
    assert loaded.job_id == legacy_id
    assert loaded.status is JobStatus.PENDING

    running = jobs.start(legacy_id)
    assert running.status is JobStatus.RUNNING
    checkpointed = jobs.checkpoint(legacy_id, {"resume": 1})
    assert checkpointed.checkpoint == {"resume": 1}

    # The compatibility path does not weaken the limit for newly-created IDs.
    with pytest.raises(ValueError, match="job_id exceeds"):
        jobs.create("scan", {}, job_id=legacy_id)
