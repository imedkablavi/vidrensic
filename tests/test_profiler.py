from __future__ import annotations

from pathlib import Path

from vidrensic.profiler.source import profile_source


def test_source_profiler_finds_known_signatures_and_hashes_samples(tmp_path: Path) -> None:
    source = tmp_path / "dvr.img"
    data = bytearray(2 * 1024 * 1024)
    data[1024:1031] = b"WFS 0.5"
    data[600_000:600_004] = b"DHAV"
    data[1_200_000:1_200_005] = b"\x00\x00\x00\x01\x67"
    source.write_bytes(data)

    profile = profile_source(source, sample_size=512 * 1024, sample_count=5)
    assert profile.sampling_only
    assert profile.aggregate_signatures["wfs_0_5_ascii"] >= 1
    assert profile.aggregate_signatures["dahua_dhav_header"] >= 1
    assert profile.aggregate_signatures["h264_sps_annexb4"] >= 1
    assert profile.samples
    assert all(len(sample.sha256) == 64 for sample in profile.samples)
    assert all(0.0 <= sample.entropy_bits_per_byte <= 8.0 for sample in profile.samples)


def test_source_profiler_is_bounded(tmp_path: Path) -> None:
    source = tmp_path / "large.img"
    source.write_bytes(bytes(4 * 1024 * 1024))
    profile = profile_source(source, sample_size=64 * 1024, sample_count=3)
    assert len(profile.samples) == 3
    assert sum(sample.size for sample in profile.samples) <= 3 * 64 * 1024


def test_profile_json_contains_sampling_warning(tmp_path: Path) -> None:
    source = tmp_path / "sample.img"
    source.write_bytes(b"WFS 0.4" + bytes(1024))
    profile = profile_source(source, sample_size=256, sample_count=2)
    output = profile.write_json(tmp_path / "profile.json")
    text = output.read_text(encoding="utf-8")
    assert '"sampling_only": true' in text
    assert "not a complete source scan" in text
