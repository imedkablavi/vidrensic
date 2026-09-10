from __future__ import annotations

from pathlib import Path
import json
from types import SimpleNamespace

from vidrensic import profiler_cli


def _bundle():
    return SimpleNamespace(
        source={"kind": "file", "size_bucket": "1–4 GiB"},
        format_detection={"results": [{"plugin": "wfs"}]},
        workflow={"review_required": True},
        to_dict=lambda: {
            "schema_version": 1,
            "bundle_type": "anonymized-profiler-bundle",
            "source": {"kind": "file", "size_bucket": "1–4 GiB"},
        },
        write_json=lambda output, replace=False: output,
    )


def test_profiler_cli_default_output_is_privacy_focused(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "recorder.img"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(profiler_cli, "triage_source", lambda *args, **kwargs: object())
    monkeypatch.setattr(profiler_cli, "build_anonymized_bundle", lambda report: _bundle())

    assert profiler_cli.main([str(source), "--out", str(tmp_path / "bundle.json")]) == 0
    output = capsys.readouterr().out
    assert "Profiler bundle ready" in output
    assert "Privacy      Evidence not included" in output
    assert "serial" not in output.lower()
    assert "sha256" not in output.lower()


def test_profiler_cli_json_is_machine_readable(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "recorder.img"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(profiler_cli, "triage_source", lambda *args, **kwargs: object())
    monkeypatch.setattr(profiler_cli, "build_anonymized_bundle", lambda report: _bundle())

    assert profiler_cli.main([str(source), "--out", str(tmp_path / "bundle.json"), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["bundle_type"] == "anonymized-profiler-bundle"
