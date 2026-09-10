from __future__ import annotations

from pathlib import Path
import json

from vidrensic import export_cli


def test_export_cli_is_concise(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "export.bin"
    manifest = tmp_path / "export.json"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(
        export_cli,
        "export_evidence",
        lambda *args, **kwargs: {
            "export_profile": "master",
            "copy": {"verified": True},
        },
    )

    assert export_cli.main([str(source), "--out", str(destination), "--manifest", str(manifest)]) == 0
    output = capsys.readouterr().out
    assert "Export complete" in output
    assert "Integrity    Verified" in output
    assert "sha256" not in output


def test_export_cli_json_is_machine_readable(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "export.bin"
    manifest = tmp_path / "export.json"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(
        export_cli,
        "export_evidence",
        lambda *args, **kwargs: {"schema_version": 1, "export_profile": "review"},
    )

    assert export_cli.main(
        [str(source), "--out", str(destination), "--manifest", str(manifest), "--json"]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
