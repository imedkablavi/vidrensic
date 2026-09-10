from pathlib import Path
from types import SimpleNamespace

from vidrensic.core.models import EvidenceStatus
from vidrensic import forensic_scan_cli


class _FakeReport:
    artifact = Path("candidate.mp4")
    profile = "standard"
    status = EvidenceStatus.REVIEW
    confidence_level = "Moderate"
    evidence_intervals = ()
    sha256_before = "a" * 64
    sha512_before = "b" * 128
    sha256_after = "a" * 64
    findings = ()

    def write_json(self, output: Path, *, replace: bool = False) -> Path:
        output.write_text("{}\n", encoding="utf-8")
        return output

    def to_dict(self) -> dict:
        return {"status": self.status.value, "profile": self.profile}


def test_forensic_scan_cli_returns_review_exit_code(monkeypatch, capsys, tmp_path: Path) -> None:
    source = tmp_path / "candidate.mp4"
    source.write_bytes(b"video")
    output = tmp_path / "scan.json"
    monkeypatch.setattr(forensic_scan_cli, "run_forensic_scan", lambda *args, **kwargs: _FakeReport())

    result = forensic_scan_cli.main([str(source), "--out", str(output)])

    assert result == 3
    assert output.exists()
    text = capsys.readouterr().out
    assert "Forensic media scan complete" in text
    assert "Verdict      REVIEW" in text
    assert "Confidence   Moderate" in text
    assert "Intervals    0" in text


def test_forensic_scan_cli_json_emits_machine_readable_status(monkeypatch, capsys, tmp_path: Path) -> None:
    source = tmp_path / "candidate.mp4"
    source.write_bytes(b"video")
    output = tmp_path / "scan.json"
    monkeypatch.setattr(forensic_scan_cli, "run_forensic_scan", lambda *args, **kwargs: _FakeReport())

    result = forensic_scan_cli.main([str(source), "--out", str(output), "--json"])

    assert result == 3
    assert '"status": "REVIEW"' in capsys.readouterr().out


def test_forensic_scan_cli_rejects_invalid_profile(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "candidate.mp4"
    source.write_bytes(b"video")
    output = tmp_path / "scan.json"
    monkeypatch.setattr(forensic_scan_cli, "run_forensic_scan", lambda *args, **kwargs: SimpleNamespace())

    try:
        forensic_scan_cli.main([str(source), "--out", str(output), "--profile", "invalid"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("invalid profile should be rejected")
