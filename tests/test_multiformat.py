from __future__ import annotations

from pathlib import Path
import json
import struct

from vidrensic.cli import default_registry, main
from vidrensic.plugins.capabilities import SupportLevel
from vidrensic.plugins.dhav.codec import parse_header
from vidrensic.plugins.dhav.scanner import demux_dhav_range, scan_dhav_frames
from vidrensic.profiler.storage import profile_storage
from vidrensic.profiles import default_profile_registry


def _packed_time(year: int, month: int, day: int, hour: int, minute: int, second: int) -> int:
    return (
        ((year - 2000) & 0x3F) << 26
        | (month & 0x0F) << 22
        | (day & 0x1F) << 17
        | (hour & 0x1F) << 12
        | (minute & 0x3F) << 6
        | (second & 0x3F)
    )


def _dhav_frame(channel: int, frame_number: int, *, second: int = 0) -> bytes:
    payload = b"\x00\x00\x00\x01\x67" + bytes([channel]) * 32
    frame_length = 24 + len(payload) + 8
    header = bytearray(24)
    header[0:4] = b"DHAV"
    header[4] = 0xFD
    header[5] = 0
    header[6] = channel
    header[7] = 0
    struct.pack_into("<I", header, 8, frame_number)
    struct.pack_into("<I", header, 12, frame_length)
    struct.pack_into("<I", header, 16, _packed_time(2026, 8, 9, 12, 0, second))
    struct.pack_into("<H", header, 20, 100)
    header[22] = 0
    header[23] = 0
    footer = b"dhav" + struct.pack("<I", frame_length)
    return bytes(header) + payload + footer


def test_dhav_header_scan_and_demux(tmp_path: Path) -> None:
    source = tmp_path / "dhav.raw"
    data = bytearray(b"X" * 123)
    data += _dhav_frame(0, 1, second=0)
    data += b"noise"
    data += _dhav_frame(1, 10, second=1)
    data += _dhav_frame(0, 2, second=2)
    source.write_bytes(data)

    first = parse_header(bytes(data[123 : 123 + 24]))
    assert first.channel == 0
    assert first.timestamp is not None
    assert first.timestamp.year == 2026

    frames = scan_dhav_frames(source)
    assert len(frames) == 3
    assert {frame.header.channel for frame in frames} == {0, 1}
    assert all(frame.structurally_valid for frame in frames)
    assert all(frame.codec_hint == "h264" for frame in frames)

    out = tmp_path / "demux"
    manifest_path = demux_dhav_range(source, out)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["frame_count"] == 3
    assert len(manifest["channels"]) == 2
    assert (out / "channel_00.native.dhav").exists()
    assert (out / "channel_01.native.dhav").exists()
    assert (out / "channel_00.video.es").exists()


def test_dhav_rejects_bad_footer_by_default(tmp_path: Path) -> None:
    source = tmp_path / "bad.raw"
    frame = bytearray(_dhav_frame(2, 1))
    frame[-8:-4] = b"FAIL"
    source.write_bytes(frame)
    assert scan_dhav_frames(source) == []
    loose = scan_dhav_frames(source, strict_footer=False)
    assert len(loose) == 1
    assert not loose[0].structurally_valid


def test_storage_profiler_detects_mbr_partition_and_ext(tmp_path: Path) -> None:
    source = tmp_path / "disk.img"
    image = bytearray(4 * 1024 * 1024)
    # One Linux-looking MBR partition beginning at LBA 2048.
    entry = 446
    image[entry] = 0
    image[entry + 4] = 0x83
    struct.pack_into("<I", image, entry + 8, 2048)
    struct.pack_into("<I", image, entry + 12, 4096)
    image[510:512] = b"\x55\xaa"
    base = 2048 * 512
    image[base + 1024 + 56 : base + 1024 + 58] = b"\x53\xef"
    source.write_bytes(image)

    report = profile_storage(source)
    assert report.partition_scheme == "MBR"
    assert len(report.partitions) == 1
    assert report.partitions[0].start_lba == 2048
    assert any(hit.family == "EXT2/3/4 family" for hit in report.filesystems)


def test_format_registry_exposes_capabilities_and_ranked_detection(tmp_path: Path) -> None:
    source = tmp_path / "sample.dhav"
    source.write_bytes(_dhav_frame(3, 1) * 10)
    registry = default_registry()
    assert {"wfs", "dhav", "annexb", "mpegps"}.issubset(set(registry.names()))
    assert registry.get("wfs").descriptor.supports(SupportLevel.PARSE)
    report = registry.detection_report(source)
    assert report.best.plugin == "dhav"
    assert report.best.confidence >= 0.78


def test_variant_profile_pack_is_data_driven(tmp_path: Path) -> None:
    pack = tmp_path / "profiles.json"
    pack.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": [
                    {
                        "profile_id": "test-wfs-model",
                        "family_id": "wfs",
                        "variant": "Lab model",
                        "vendor_patterns": ["acme*"],
                        "model_patterns": ["dvr-42*"],
                        "firmware_patterns": ["1.2.*"],
                        "parameters": {"fragment_size": 1048576},
                        "validation_state": "lab-only",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    registry = default_profile_registry()
    loaded = registry.load_pack(pack)
    assert loaded[0].parameters["fragment_size"] == 1048576
    matches = registry.match(vendor="Acme Inc", model="DVR-4200", firmware="1.2.9")
    assert matches[0][1].profile_id == "test-wfs-model"
    assert matches[0][0] > 0.9


def test_multiformat_cli_surfaces_matrix_and_detection(tmp_path: Path, capsys) -> None:
    assert main(["formats", "list"]) == 0
    listed = capsys.readouterr().out
    assert "wfs" in listed
    assert "dhav" in listed

    source = tmp_path / "sample.dhav"
    source.write_bytes(_dhav_frame(1, 1) * 10)
    code = main(["formats", "detect", str(source)])
    assert code == 0
    detected = capsys.readouterr().out
    assert "dhav" in detected
