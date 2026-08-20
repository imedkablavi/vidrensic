from pathlib import Path

from cvf.acquisition.ddrescue import AcquisitionPlan
from cvf.core.audit import AuditLog
from cvf.core.case import Case
from cvf.plugins.wfs.profile import WFSProfile, WFS_FRAGMENT_SIZE


def test_case_creation(tmp_path: Path):
    case = Case.create(tmp_path, "CASE-001")
    assert (case.root / "case.json").exists()
    assert (case.root / "evidence").is_dir()
    assert (case.root / "exports").is_dir()


def test_audit_chain_detects_tamper(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path)
    audit.append("case_created", {"case": "CASE-001"})
    audit.append("source_added", {"path": "/dev/sdb"})
    assert audit.verify()

    text = path.read_text(encoding="utf-8").replace("CASE-001", "CASE-999", 1)
    path.write_text(text, encoding="utf-8")
    assert not audit.verify()


def test_ddrescue_plan_is_argument_vector():
    plan = AcquisitionPlan(
        source=Path("/dev/sdb"),
        image=Path("/cases/image.raw"),
        mapfile=Path("/cases/image.map"),
        input_offset=4096,
        size_bytes=8192,
    )
    assert plan.command() == [
        "ddrescue", "-f", "-n", "-i", "4096", "-o", "0", "-s", "8192",
        "/dev/sdb", "/cases/image.raw", "/cases/image.map",
    ]


def test_wfs_profile():
    profile = WFSProfile()
    assert profile.fragment_size == WFS_FRAGMENT_SIZE == 2 * 1024 * 1024
    assert profile.record_prefix_known(b"\x00\x00\x01\xfdmore")
    assert not profile.record_prefix_known(b"NOPE")
