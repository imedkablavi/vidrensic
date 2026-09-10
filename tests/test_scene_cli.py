from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from vidrensic import scene_cli


def _report(path: Path, output: Path):
    return SimpleNamespace(
        artifact=path,
        duration_seconds=120.0,
        requested_sample_count=24,
        approximate_interval_seconds=5.0,
        columns=5,
        rows=5,
        output=output,
        source_sha256="a" * 64,
        source_sha512="b" * 128,
        output_sha256="c" * 64,
        output_sha512="d" * 128,
        output_size_bytes=1234,
        to_dict=lambda: {
            "schema_version": 1,
            "scene_sampling": {"derived": True, "requested_sample_count": 24},
        },
        write_json=lambda manifest: manifest,
    )


def test_scene_cli_human_output(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "video.mp4"
    output = tmp_path / "sheet.png"
    source.write_bytes(b"video")
    monkeypatch.setattr(scene_cli, "create_contact_sheet", lambda *args, **kwargs: _report(source, output))

    assert scene_cli.main([str(source), "--out", str(output)]) == 0
    text = capsys.readouterr().out
    assert "Contact sheet created" in text
    assert "Derived      Yes — visual triage only" in text
    assert "Grid         5 × 5" in text


def test_scene_cli_json(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "video.mp4"
    output = tmp_path / "sheet.png"
    source.write_bytes(b"video")
    monkeypatch.setattr(scene_cli, "create_contact_sheet", lambda *args, **kwargs: _report(source, output))

    assert scene_cli.main([str(source), "--out", str(output), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["scene_sampling"]["derived"] is True


def test_scene_cli_rejects_zero_samples() -> None:
    assert scene_cli.main(["video.mp4", "--out", "sheet.png", "--samples", "0"]) == 2


def test_scene_cli_cleans_sheet_when_manifest_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "video.mp4"
    output = tmp_path / "sheet.png"
    source.write_bytes(b"video")

    def fake_create(*args, **kwargs):
        output.write_bytes(b"derived")
        report = _report(source, output)
        report.write_json = lambda _manifest: (_ for _ in ()).throw(OSError("manifest write failed"))
        return report

    monkeypatch.setattr(scene_cli, "create_contact_sheet", fake_create)

    assert scene_cli.main([str(source), "--out", str(output)]) == 2
    assert output.exists() is False
