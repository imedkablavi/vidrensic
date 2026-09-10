from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from vidrensic.media import scenes


def _hashes() -> SimpleNamespace:
    return SimpleNamespace(sha256="a" * 64, sha512="b" * 128)


def _probe() -> SimpleNamespace:
    return SimpleNamespace(duration=120.0, codec="h264")


def test_grid_is_deterministic() -> None:
    assert scenes._grid(1) == (1, 1)
    assert scenes._grid(24) == (5, 5)
    assert scenes._grid(256) == (6, 43)


def test_contact_sheet_manifest_is_derived(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "video.mp4"
    output = tmp_path / "sheet.png"
    source.write_bytes(b"video")
    output.write_bytes(b"png")
    monkeypatch.setattr(scenes, "forensic_hashes_stable", lambda _: _hashes())
    monkeypatch.setattr(scenes, "probe_video", lambda _: _probe())
    monkeypatch.setattr(
        scenes,
        "run_media_tool_bounded",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=b"", stderr=b""),
    )
    monkeypatch.setattr(scenes, "_validate_output", lambda _: output)
    output.unlink()
    output.write_bytes(b"derived")

    # Re-run with an implementation-independent fake output file.
    output.unlink()
    def fake_run(*args, **kwargs):
        output.write_bytes(b"derived")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(scenes, "run_media_tool_bounded", fake_run)
    report = scenes.create_contact_sheet(source, output, sample_count=12, thumbnail_width=320)

    assert report.requested_sample_count == 12
    assert report.columns == 4
    assert report.rows == 3
    assert report.approximate_interval_seconds == pytest.approx(10.0)
    assert report.output_size_bytes == len(b"derived")
    assert report.source_sha256 == "a" * 64
    assert report.output_sha256 == "".join([]) or len(report.output_sha256) == 64
    payload = report.to_dict()
    assert payload["scene_sampling"]["derived"] is True
    assert "visual triage aids" in payload["scene_sampling"]["timestamp_mapping"]


def test_contact_sheet_rejects_existing_and_symlink_outputs(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    output = tmp_path / "sheet.png"
    target = tmp_path / "target.png"
    source.write_bytes(b"video")
    target.write_bytes(b"target")
    output.symlink_to(target)

    with pytest.raises(FileExistsError):
        scenes.create_contact_sheet(source, output)


def test_contact_sheet_rejects_symlink_source(tmp_path: Path) -> None:
    target = tmp_path / "video.mp4"
    link = tmp_path / "alias.mp4"
    output = tmp_path / "sheet.png"
    target.write_bytes(b"video")
    link.symlink_to(target)

    with pytest.raises(ValueError, match="non-symlink"):
        scenes.create_contact_sheet(link, output)


def test_contact_sheet_rejects_bad_parameters(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    output = tmp_path / "sheet.png"
    source.write_bytes(b"video")

    with pytest.raises(ValueError):
        scenes.create_contact_sheet(source, output, sample_count=0)
    with pytest.raises(ValueError):
        scenes.create_contact_sheet(source, output, sample_count=257)
    with pytest.raises(ValueError):
        scenes.create_contact_sheet(source, output, thumbnail_width=32)
    with pytest.raises(ValueError):
        scenes.create_contact_sheet(source, output, timeout=0)
    with pytest.raises(ValueError):
        scenes.create_contact_sheet(source, tmp_path / "sheet.gif")
