from __future__ import annotations

from pathlib import Path
import json

import pytest

from vidrensic.acquisition.ddrescue import AcquisitionPlan
from vidrensic.core.audit import AuditLog
from vidrensic.core.case import Case
from vidrensic.core.hashing import forensic_hashes
from vidrensic.core.jobs import JobStatus


def test_case_create_and_audit(tmp_path: Path) -> None:
    case = Case.create(tmp_path, "CASE-001", examiner="tester")
    assert case.case_id == "CASE-001"
    assert (case.root / "derived" / "native").is_dir()
    assert (case.root / "derived" / "review").is_dir()
    assert (case.root / "state" / "jobs.sqlite3").is_file()
    ok, tail = case.audit.verify()
    assert ok
    assert len(tail) == 64
    loaded = Case.load(case.root)
    assert loaded.case_uuid == case.case_uuid


def test_case_id_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        Case.create(tmp_path, "../escape")


def test_case_safe_path(tmp_path: Path) -> None:
    case = Case.create(tmp_path, "CASE-002")
    assert case.safe_path("reports", "x.json") == case.root / "reports" / "x.json"
    with pytest.raises(ValueError):
        case.safe_path("..", "other")


def test_audit_tamper_detection(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path)
    audit.append("one", {"value": 1})
    audit.append("two", {"value": 2})
    ok, _ = audit.verify()
    assert ok

    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["details"]["value"] = 999
    lines[0] = json.dumps(record, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, reason = audit.verify()
    assert not ok
    assert "mismatch" in reason


def test_forensic_hashes(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(b"vidrensic")
    hashes = forensic_hashes(path)
    assert len(hashes.sha256) == 64
    assert hashes.sha512 is not None
    assert len(hashes.sha512) == 128


def test_ddrescue_plan_is_bounded_and_resumable(tmp_path: Path) -> None:
    source = tmp_path / "source.img"
    source.write_bytes(b"x")
    output = tmp_path / "out.raw"
    plan = AcquisitionPlan(
        source=source,
        output=output,
        mapfile=tmp_path / "out.map",
        offset=4096,
        size=8192,
        retry_passes=1,
    )
    first = plan.first_pass_command()
    retry = plan.retry_command()
    assert first[:3] == ["ddrescue", "-f", "-n"]
    assert ["-i", "4096"] == first[first.index("-i") : first.index("-i") + 2]
    assert ["-s", "8192"] == first[first.index("-s") : first.index("-s") + 2]
    assert str(plan.mapfile) == first[-1]
    assert retry is not None
    assert "-r1" in retry
    assert plan.additional_required_bytes == 8192

    output.write_bytes(bytes(3000))
    assert plan.additional_required_bytes == 5192


def test_job_store_checkpoint_and_resume(tmp_path: Path) -> None:
    case = Case.create(tmp_path, "CASE-JOBS", examiner="tester")
    job = case.jobs.create(
        "wfs.recover",
        {"source": "evidence.raw", "label": "09-00"},
    )
    assert job.status is JobStatus.PENDING

    job = case.jobs.start(job.job_id)
    assert job.status is JobStatus.RUNNING

    job = case.jobs.checkpoint(
        job.job_id,
        {"last_fragment": 1234, "candidate": 2},
        progress_current=40,
        progress_total=100,
    )
    assert job.checkpoint["last_fragment"] == 1234
    assert job.progress_fraction == pytest.approx(0.4)

    job = case.jobs.pause(job.job_id)
    assert job.status is JobStatus.PAUSED
    job = case.jobs.start(job.job_id)
    job = case.jobs.complete(job.job_id)
    assert job.status is JobStatus.COMPLETED

    reopened = Case.load(case.root).jobs.get(job.job_id)
    assert reopened.status is JobStatus.COMPLETED
    assert reopened.checkpoint["candidate"] == 2
    with pytest.raises(ValueError):
        case.jobs.checkpoint(job.job_id, {"invalid": True})


def test_job_store_rejects_invalid_transitions(tmp_path: Path) -> None:
    case = Case.create(tmp_path, "CASE-JOB-STATE")
    job = case.jobs.create("scan", {})
    with pytest.raises(ValueError):
        case.jobs.complete(job.job_id)
    job = case.jobs.start(job.job_id)
    job = case.jobs.fail(job.job_id, "synthetic failure")
    assert job.error == "synthetic failure"
    with pytest.raises(ValueError):
        case.jobs.start(job.job_id)
