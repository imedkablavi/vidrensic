from pathlib import Path
from types import SimpleNamespace

import pytest

from vidrensic.media import proxy


def _hashes(value: str):
    return SimpleNamespace(sha256=value, sha512=value + "512")


def _probe():
    return SimpleNamespace(
        codec="h264",
        duration=10.0,
        width=1920,
        height=1080,
        stream_count=1,
    )


def _tool_result():
    return SimpleNamespace(returncode=0, stdout=b"", stderr=b"", stdout_truncated=False)


def test_transcode_proxy_publishes_verified_output(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "proxy.mp4"
    source.write_bytes(b"source")
    stable = iter([
        _hashes("source"),
        _hashes("output"),
        _hashes("source"),
        _hashes("output"),
    ])

    monkeypatch.setattr(proxy, "forensic_hashes_stable", lambda _path: next(stable))
    monkeypatch.setattr(proxy, "probe_video", lambda _path: _probe())
    monkeypatch.setattr(proxy, "decode_window", lambda *args, **kwargs: (True, ""))

    def fake_ffmpeg(_name, args, **_kwargs):
        Path(args[-1]).write_bytes(b"derived")
        return _tool_result()

    monkeypatch.setattr(proxy, "run_media_tool_bounded", fake_ffmpeg)

    report = proxy.transcode_proxy(source, destination)

    assert destination.read_bytes() == b"derived"
    assert report.source_sha256 == "source"
    assert report.destination_sha256 == "output"
    assert report.decode_smoke_tested is True


def test_transcode_proxy_rejects_existing_output(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "proxy.mp4"
    source.write_bytes(b"source")
    destination.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        proxy.transcode_proxy(source, destination)


def test_transcode_proxy_requires_mp4_output(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")

    with pytest.raises(ValueError, match=r"\.mp4"):
        proxy.transcode_proxy(source, tmp_path / "proxy.mkv")


def test_transcode_proxy_fails_closed_on_decode_failure(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "proxy.mp4"
    source.write_bytes(b"source")
    hashes = iter([_hashes("source"), _hashes("output")])

    monkeypatch.setattr(proxy, "forensic_hashes_stable", lambda _path: next(hashes))
    monkeypatch.setattr(proxy, "probe_video", lambda _path: _probe())
    monkeypatch.setattr(proxy, "decode_window", lambda *args, **kwargs: (False, "decode failed"))

    def fake_ffmpeg(_name, args, **_kwargs):
        Path(args[-1]).write_bytes(b"derived")
        return _tool_result()

    monkeypatch.setattr(proxy, "run_media_tool_bounded", fake_ffmpeg)

    with pytest.raises(proxy.ProxyIntegrityError, match="decode smoke test failed"):
        proxy.transcode_proxy(source, destination)
    assert not destination.exists()


def test_transcode_proxy_rejects_source_mutation(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "proxy.mp4"
    source.write_bytes(b"source")
    hashes = iter([_hashes("before"), _hashes("output"), _hashes("after")])

    monkeypatch.setattr(proxy, "forensic_hashes_stable", lambda _path: next(hashes))
    monkeypatch.setattr(proxy, "probe_video", lambda _path: _probe())
    monkeypatch.setattr(proxy, "decode_window", lambda *args, **kwargs: (True, ""))

    def fake_ffmpeg(_name, args, **_kwargs):
        Path(args[-1]).write_bytes(b"derived")
        return _tool_result()

    monkeypatch.setattr(proxy, "run_media_tool_bounded", fake_ffmpeg)

    with pytest.raises(proxy.ProxyIntegrityError, match="source changed"):
        proxy.transcode_proxy(source, destination)
    assert not destination.exists()


def test_transcode_proxy_manifest_failure_removes_output(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "proxy.mp4"
    manifest = tmp_path / "proxy.json"
    source.write_bytes(b"source")
    stable = iter([_hashes("source"), _hashes("output"), _hashes("source"), _hashes("output")])

    monkeypatch.setattr(proxy, "forensic_hashes_stable", lambda _path: next(stable))
    monkeypatch.setattr(proxy, "probe_video", lambda _path: _probe())
    monkeypatch.setattr(proxy, "decode_window", lambda *args, **kwargs: (True, ""))

    def fake_ffmpeg(_name, args, **_kwargs):
        Path(args[-1]).write_bytes(b"derived")
        return _tool_result()

    monkeypatch.setattr(proxy, "run_media_tool_bounded", fake_ffmpeg)
    monkeypatch.setattr(proxy.ProxyReport, "write_json", lambda _self, _output: (_ for _ in ()).throw(OSError("manifest failed")))

    with pytest.raises(OSError, match="manifest failed"):
        proxy.transcode_proxy_with_manifest(source, destination, manifest)
    assert not destination.exists()
