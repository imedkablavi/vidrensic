from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from vidrensic import proxy_cli


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
        source_codec="h264",
        destination_codec="h264",
        source_width=1920,
        source_height=1080,
        destination_width=1920,
        destination_height=1080,
        source_stream_count=1,
        destination_stream_count=1,
        decode_smoke_tested=True,
        to_dict=lambda: {
            "schema_version": 1,
            "proxy": {"derived": True, "profile": "review-h264-aac", "transcoded": True},
        },
    )


def test_proxy_cli_human_output(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "proxy.mp4"
    manifest = tmp_path / "proxy.json"
    source.write_bytes(b"source")

    def fake_proxy(source_path, destination, manifest_path):
        destination.write_bytes(b"derived")
        manifest_path.write_text("{}\n", encoding="utf-8")
        return _report(destination)

    monkeypatch.setattr(proxy_cli, "transcode_proxy_with_manifest", fake_proxy)

    assert proxy_cli.main([str(source), "--out", str(output), "--manifest", str(manifest)]) == 0
    text = capsys.readouterr().out
    assert "Review proxy created" in text
    assert "H.264/AAC MP4" in text
    assert "Derived      Yes — review proxy only" in text
    assert "Decode QC    Passed" in text


def test_proxy_cli_json_output(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "proxy.mp4"
    manifest = tmp_path / "proxy.json"
    source.write_bytes(b"source")
    monkeypatch.setattr(
        proxy_cli,
        "transcode_proxy_with_manifest",
        lambda source_path, destination, manifest_path: _report(destination),
    )

    assert proxy_cli.main([str(source), "--out", str(output), "--manifest", str(manifest), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["proxy"]["profile"] == "review-h264-aac"


def test_proxy_cli_rejects_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "proxy.mp4"
    output.write_bytes(b"existing")
    with pytest.raises(SystemExit) as exc:
        proxy_cli.main(["source.mp4", "--out", str(output), "--manifest", str(tmp_path / "p.json")])
    assert exc.value.code == 2


def test_proxy_cli_rejects_non_mp4_output_before_engine(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        proxy_cli.main(["source.mp4", "--out", str(tmp_path / "proxy.mkv"), "--manifest", str(tmp_path / "p.json")])
    assert exc.value.code == 2
