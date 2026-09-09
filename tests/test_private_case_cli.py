from __future__ import annotations

from pathlib import Path
import json
import stat

from vidrensic.cli_ext import main


def test_private_case_cli_creates_restricted_manifest(tmp_path: Path, capsys) -> None:
    source = tmp_path / "evidence" / "recorder.raw"
    source.parent.mkdir()
    source.write_bytes(b"real-recorder-placeholder")
    output = tmp_path / "private-case.json"

    assert (
        main(
            [
                "validate",
                "private-case",
                str(source),
                "--out",
                str(output),
                "--case-id",
                "lab-wfs-001",
                "--family",
                "wfs",
                "--manufacturer",
                "Example",
                "--model",
                "Recorder-1",
                "--firmware",
                "1.0",
                "--note",
                "restricted lab fixture",
            ]
        )
        == 0
    )

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["manifest_type"] == "private-validation-case"
    assert data["source"]["path"] == "evidence/recorder.raw"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    stdout = capsys.readouterr().out
    assert "manifest=" in stdout
    assert "source_sha256=" in stdout
    assert "source_size_bytes=" in stdout
