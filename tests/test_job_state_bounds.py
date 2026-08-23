from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from vidrensic.core.jobs import (
    MAX_JOB_ERROR_CHARS,
    MAX_JOB_ID_CHARS,
    MAX_JOB_JSON_CHARS,
    MAX_JOB_KIND_CHARS,
    JobStore,
)


def _store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / "jobs.sqlite3")


def test_job_create_rejects_oversized_kind_id_and_metadata(tmp_path: Path) -> None:
    jobs = _store(tmp_path)
    with pytest.raises(ValueError, match="job kind exceeds"):
        jobs.create("K" * (MAX_JOB_KIND_CHARS + 1), {})
    with pytest.raises(ValueError, match="job_id exceeds"):
        jobs.create("scan", {}, job_id="J" * (MAX_JOB_ID_CHARS + 1))
    with pytest.raises(ValueError, match="job metadata exceeds"):
        jobs.create("scan", {"blob": "X" * (MAX_JOB_JSON_CHARS + 1)})


def test_job_checkpoint_and_error_are_bounded_before_database_write(tmp_path: Path) -> None:
    jobs = _store(tmp_path)
    job = jobs.create("scan", {})
    job = jobs.start(job.job_id)

    with pytest.raises(ValueError, match="job metadata exceeds"):
        jobs.checkpoint(job.job_id, {"blob": "X" * (MAX_JOB_JSON_CHARS + 1)})
    with pytest.raises(ValueError, match="job error exceeds"):
        jobs.fail(job.job_id, "E" * (MAX_JOB_ERROR_CHARS + 1))

    fresh = jobs.get(job.job_id)
    assert fresh.checkpoint == {}
    assert fresh.error is None


def test_safe_read_rejects_tampered_oversized_json_without_returning_text(
    tmp_path: Path,
) -> None:
    jobs = _store(tmp_path)
    job = jobs.create("scan", {"safe": True})

    with sqlite3.connect(jobs.path) as conn:
        conn.execute(
            "UPDATE jobs SET parameters_json=? WHERE job_id=?",
            ('{"blob":"' + ("X" * (MAX_JOB_JSON_CHARS + 1)) + '"}', job.job_id),
        )

    with pytest.raises(ValueError, match="stored job parameters exceeds"):
        jobs.get(job.job_id)
    with pytest.raises(ValueError, match="stored job parameters exceeds"):
        jobs.list()


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
            ("E" * (MAX_JOB_ERROR_CHARS + 1), job.job_id),
        )
    with pytest.raises(ValueError, match="stored job error exceeds"):
        jobs.get(job.job_id)
