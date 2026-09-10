from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import stat

from vidrensic.media import inventory
from vidrensic.media.probe import VideoProbe


def _probe(path: Path) -> VideoProbe:
    return VideoProbe(
        path=path,
        duration=12.5,
        codec="h264",
        width=1920,
        height=1080,
        avg_frame_rate=25.0,
        r_frame_rate=25.0,
        stream_count=2,
        raw={
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "25/1",
                    "r_frame_rate": "25/1",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "avg_frame_rate": "0/0",
                    "r_frame_rate": "0/0",
                },
            ]
        },
    )


def test_inventory_binds_stable_hashes_and_streams(tmp_path: Path, monkeypatch) -> None:
    artifact = tmp_path / "candidate.mp4"
    artifact.write_bytes(b"media")
    monkeypatch.setattr(inventory, "probe_video", lambda _path: _probe(artifact))
    monkeypatch.setattr(
        inventory,
        "forensic_hashes_stable",
        lambda _path: SimpleNamespace(sha256="a" * 64, sha512="b" * 128),
    )

    report = inventory.inspect_media(artifact)

    assert report.sha256 == "a" * 64
    assert report.sha512 == "b" * 128
    assert report.stream_count == 2
    assert report.streams[0].codec == "h264"
    assert report.streams[1].codec == "aac"
    assert report.streams[1].avg_frame_rate is None


def test_inventory_persists_private_json_without_overwrite(tmp_path: Path, monkeypatch) -> None:
    artifact = tmp_path / "candidate.mp4"
    artifact.write_bytes(b"media")
    monkeypatch.setattr(inventory, "probe_video", lambda _path: _probe(artifact))
    monkeypatch.setattr(
        inventory,
        "forensic_hashes_stable",
        lambda _path: SimpleNamespace(sha256="a" * 64, sha512="b" * 128),
    )
    report = inventory.inspect_media(artifact)
    output = tmp_path / "inventory.json"

    report.write_json(output)

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["hashes"]["sha256"] == "a" * 64
    assert len(data["media"]["streams"]) == 2
    assert stat.S_IMODE(output.stat().st_mode) == 0o600

    try:
        report.write_json(output)
    except FileExistsError:
        pass
    else:
        raise AssertionError("inventory report unexpectedly overwrote an existing file")


def test_inventory_rejects_non_regular_artifact(tmp_path: Path, monkeypatch) -> None:
    directory = tmp_path / "directory"
    directory.mkdir()
    try:
        inventory.inspect_media(directory)
    except ValueError as exc:
        assert "regular file" in str(exc)
    else:
        raise AssertionError("directory should not be accepted as media artifact")
