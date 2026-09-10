from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from vidrensic import repair_cli


def _report(destination: Path):
    return SimpleNamespace(
        source=destination.parent / "source.mp4",
        destination=destination,
        source_sha256="a" * 64,
        source_sha512="b" * 128,
        destination_sha256="c" * 64,
        destination_sha512="d" * 128,
        source_size_bytes=100,
        destination_size_bytes=120,
        source_duration_seconds=10.0,
        destination_duration_seconds=10.0,
        source_stream_count=1,
        destination_stream_count=1,
        source_codec="h264",
        destination_codec="h264",
        to_dict=lambda: {
            "schema_version": 1,
            "repair": {"derived": True, "mode": "remux", "stream_copy": True},
        },
    )


def test_repair_cli_human_output(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "repaired.mp4"
    manifest = tmp_path / "repaired.json"
    source.write_bytes(b"source")

    def fake_remux(source_path, destination, manifest_path):
        destination.write_bytes(b"derived")
        manifest_path.write_text("{}\n", encoding="utf-8")
        return _report(destination)

    monkeypatch.setattr(repair_cli, "remux_video_with_manifest", fake_remux)

    assert repair_cli.main([str(source), "--out", str(output), "--manifest", str(manifest)]) == 0
    text = capsys.readouterr().out
    assert "Repair complete" in text
    assert "Stream-copy remux" in text
    assert "Source       Unmodified" in text


def test_repair_cli_json_output(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "repaired.mp4"
    manifest = tmp_path / "repaired.json"
    source.write_bytes(b"source")

    monkeypatch.setattr(
        repair_cli,
        "remux_video_with_manifest",
        lambda source_path, destination, manifest_path: _report(destination),
    )

    assert repair_cli.main([str(source), "--out", str(output), "--manifest", str(manifest), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["repair"]["mode"] == "remux"
    assert payload["repair"]["stream_copy"] is True


def test_repair_cli_rejects_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "repaired.mp4"
    output.write_bytes(b"existing")
    with pytest.raises(SystemExit) as exc:
        repair_cli.main(["source.mp4", "--out", str(output), "--manifest", str(tmp_path / "r.json")])
    assert exc.value.code == 2


def test_repair_cli_rejects_existing_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "repaired.json"
    manifest.write_text("existing", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        repair_cli.main(["source.mp4", "--out", str(tmp_path / "r.mp4"), "--manifest", str(manifest)])
    assert exc.value.code == 2
