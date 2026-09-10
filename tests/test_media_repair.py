from pathlib import Path
from types import SimpleNamespace

import pytest

from vidrensic.media import repair


def _hashes(sha256: str, sha512: str = "b"):
    return SimpleNamespace(sha256=sha256, sha512=sha512)


def _probe():
    return SimpleNamespace(codec="h264", duration=10.0, stream_count=1)


def _tool_result():
    return SimpleNamespace(returncode=0, stdout=b"", stderr=b"", stdout_truncated=False)


def test_remux_publishes_verified_output(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "repaired.mp4"
    source.write_bytes(b"source")

    monkeypatch.setattr(repair, "forensic_hashes_stable", lambda path: _hashes("source" if path == source else "output"))
    monkeypatch.setattr(repair, "probe_video", lambda _path: _probe())

    def fake_ffmpeg(_name, args, **_kwargs):
        Path(args[-1]).write_bytes(b"derived")
        return _tool_result()

    monkeypatch.setattr(repair, "run_media_tool_bounded", fake_ffmpeg)

    report = repair.remux_video(source, destination)

    assert destination.read_bytes() == b"derived"
    assert report.source_sha256 == "source"
    assert report.destination_sha256 == "output"
    assert report.destination == destination.resolve()


def test_remux_rejects_existing_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "repaired.mp4"
    source.write_bytes(b"source")
    destination.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        repair.remux_video(source, destination)


def test_remux_fails_closed_on_ffmpeg_error(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "repaired.mp4"
    source.write_bytes(b"source")

    monkeypatch.setattr(repair, "forensic_hashes_stable", lambda _path: _hashes("source"))
    monkeypatch.setattr(repair, "probe_video", lambda _path: _probe())
    monkeypatch.setattr(
        repair,
        "run_media_tool_bounded",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout=b"",
            stderr=b"invalid stream",
            stdout_truncated=False,
        ),
    )

    with pytest.raises(repair.RepairIntegrityError, match="invalid stream"):
        repair.remux_video(source, destination)
    assert not destination.exists()


def test_remux_rejects_source_mutation(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "repaired.mp4"
    source.write_bytes(b"source")
    stable = iter([_hashes("before"), _hashes("output"), _hashes("after")])

    monkeypatch.setattr(repair, "forensic_hashes_stable", lambda _path: next(stable))
    monkeypatch.setattr(repair, "probe_video", lambda _path: _probe())

    def fake_ffmpeg(_name, args, **_kwargs):
        Path(args[-1]).write_bytes(b"derived")
        return _tool_result()

    monkeypatch.setattr(repair, "run_media_tool_bounded", fake_ffmpeg)

    with pytest.raises(repair.RepairIntegrityError, match="source changed"):
        repair.remux_video(source, destination)
    assert not destination.exists()


def test_remux_manifest_failure_removes_derived_output(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "repaired.mp4"
    manifest = tmp_path / "repaired.json"
    source.write_bytes(b"source")

    monkeypatch.setattr(repair, "forensic_hashes_stable", lambda path: _hashes("source" if path == source else "output"))
    monkeypatch.setattr(repair, "probe_video", lambda _path: _probe())

    def fake_ffmpeg(_name, args, **_kwargs):
        Path(args[-1]).write_bytes(b"derived")
        return _tool_result()

    monkeypatch.setattr(repair, "run_media_tool_bounded", fake_ffmpeg)
    monkeypatch.setattr(repair.RemuxReport, "write_json", lambda _self, _output: (_ for _ in ()).throw(OSError("manifest failed")))

    with pytest.raises(OSError, match="manifest failed"):
        repair.remux_video_with_manifest(source, destination, manifest)
    assert not destination.exists()
