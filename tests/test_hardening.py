from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import json
import struct
import threading
import zlib

import pytest

from vidrensic.acquisition.ddrescue import AcquisitionPlan, check_capacity
from vidrensic.core.audit import AuditLog
from vidrensic.core.case import Case
from vidrensic.core.jobs import JobStatus
from vidrensic.plugins.dhav.codec import parse_extension
from vidrensic.plugins.dhav.scanner import scan_dhav_frames
from vidrensic.profiler.storage import profile_storage


def _packed_time(year: int, month: int, day: int, hour: int, minute: int, second: int) -> int:
    return (
        ((year - 2000) & 0x3F) << 26
        | (month & 0x0F) << 22
        | (day & 0x1F) << 17
        | (hour & 0x1F) << 12
        | (minute & 0x3F) << 6
        | (second & 0x3F)
    )


def _dhav_extended_frame() -> bytes:
    extension = (
        bytes([0x81, 0x00, 0x0C, 15])
        + bytes([0x82, 0x00, 0x00, 0x00])
        + struct.pack("<HH", 1280, 720)
    )
    payload = b"\x00\x00\x00\x01\x40\x01" + b"video" * 12
    frame_length = 24 + len(extension) + len(payload) + 8
    header = bytearray(24)
    header[0:4] = b"DHAV"
    header[4] = 0xFD
    header[6] = 2
    struct.pack_into("<I", header, 8, 77)
    struct.pack_into("<I", header, 12, frame_length)
    struct.pack_into("<I", header, 16, _packed_time(2026, 8, 9, 12, 30, 0))
    struct.pack_into("<H", header, 20, 250)
    header[22] = len(extension)
    footer = b"dhav" + struct.pack("<I", frame_length)
    return bytes(header) + extension + payload + footer


def _write_valid_gpt(path: Path) -> None:
    sector = 512
    total_lbas = 8192
    image = bytearray(total_lbas * sector)

    # Protective MBR.
    image[446 + 4] = 0xEE
    struct.pack_into("<I", image, 446 + 8, 1)
    struct.pack_into("<I", image, 446 + 12, total_lbas - 1)
    image[510:512] = b"\x55\xaa"

    count = 128
    entry_size = 128
    table = bytearray(count * entry_size)
    table[0:16] = bytes.fromhex("A2A0D0EBE5B9334487C068B6B72699C7")
    table[16:32] = bytes.fromhex("00112233445566778899AABBCCDDEEFF")
    struct.pack_into("<Q", table, 32, 2048)
    struct.pack_into("<Q", table, 40, 4095)
    name = "Evidence".encode("utf-16le")
    table[56 : 56 + len(name)] = name
    table_crc = zlib.crc32(table) & 0xFFFFFFFF
    image[2 * sector : 2 * sector + len(table)] = table

    header = bytearray(sector)
    header[:8] = b"EFI PART"
    struct.pack_into("<I", header, 8, 0x00010000)
    struct.pack_into("<I", header, 12, 92)
    struct.pack_into("<Q", header, 24, 1)
    struct.pack_into("<Q", header, 32, total_lbas - 1)
    struct.pack_into("<Q", header, 40, 34)
    struct.pack_into("<Q", header, 48, total_lbas - 34)
    header[56:72] = bytes.fromhex("11223344556677889900AABBCCDDEEFF")
    struct.pack_into("<Q", header, 72, 2)
    struct.pack_into("<I", header, 80, count)
    struct.pack_into("<I", header, 84, entry_size)
    struct.pack_into("<I", header, 88, table_crc)
    header_for_crc = bytearray(header[:92])
    header_for_crc[16:20] = b"\x00" * 4
    struct.pack_into("<I", header, 16, zlib.crc32(header_for_crc) & 0xFFFFFFFF)
    image[sector : 2 * sector] = header
    path.write_bytes(image)


def test_acquisition_geometry_and_full_capacity_preflight(tmp_path: Path, monkeypatch) -> None:
    plan = AcquisitionPlan(
        source=tmp_path / "source.raw",
        output=tmp_path / "out.raw",
        mapfile=tmp_path / "out.map",
        offset=100,
    )
    assert plan.validate_source_geometry(1000) == 900

    too_large = AcquisitionPlan(
        source=tmp_path / "source.raw",
        output=tmp_path / "big.raw",
        mapfile=tmp_path / "big.map",
        offset=100,
        size=901,
    )
    with pytest.raises(ValueError):
        too_large.validate_source_geometry(1000)

    monkeypatch.setattr("vidrensic.acquisition.ddrescue._filesystem_type", lambda _: "ext4")
    monkeypatch.setattr(
        "vidrensic.acquisition.ddrescue.shutil.disk_usage",
        lambda _: SimpleNamespace(free=10_000),
    )
    check_capacity(plan, source_size=1000, reserve_bytes=0)

    monkeypatch.setattr(
        "vidrensic.acquisition.ddrescue.shutil.disk_usage",
        lambda _: SimpleNamespace(free=100),
    )
    with pytest.raises(OSError):
        check_capacity(plan, source_size=1000, reserve_bytes=0)


def test_capacity_rejects_fat32_single_large_image(tmp_path: Path, monkeypatch) -> None:
    plan = AcquisitionPlan(
        source=tmp_path / "source.raw",
        output=tmp_path / "out.raw",
        mapfile=tmp_path / "out.map",
        size=5 * 1024**3,
    )
    monkeypatch.setattr("vidrensic.acquisition.ddrescue._filesystem_type", lambda _: "vfat")
    monkeypatch.setattr(
        "vidrensic.acquisition.ddrescue.shutil.disk_usage",
        lambda _: SimpleNamespace(free=20 * 1024**3),
    )
    with pytest.raises(OSError, match="cannot safely hold"):
        check_capacity(plan, source_size=6 * 1024**3, reserve_bytes=0)


def test_audit_concurrent_appends_keep_one_linear_hash_chain(tmp_path: Path) -> None:
    audit = AuditLog(tmp_path / "audit.jsonl")
    barrier = threading.Barrier(16)

    def worker(index: int) -> None:
        barrier.wait()
        audit.append("concurrent", {"index": index})

    with ThreadPoolExecutor(max_workers=16) as executor:
        list(executor.map(worker, range(16)))

    ok, tail = audit.verify()
    assert ok
    assert len(tail) == 64
    records = [json.loads(line) for line in audit.path.read_text(encoding="utf-8").splitlines()]
    assert [record["seq"] for record in records] == list(range(1, 17))
    assert {record["details"]["index"] for record in records} == set(range(16))


def test_job_race_allows_only_one_stale_transition(tmp_path: Path) -> None:
    case = Case.create(tmp_path, "CASE-RACE")
    job = case.jobs.create("race", {})
    case.jobs.start(job.job_id)
    barrier = threading.Barrier(2)

    def complete():
        barrier.wait()
        return case.jobs.complete(job.job_id)

    def pause():
        barrier.wait()
        return case.jobs.pause(job.job_id)

    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(complete), executor.submit(pause)]
        for future in futures:
            try:
                outcomes.append(future.result())
            except (ValueError, RuntimeError):
                outcomes.append(None)

    assert sum(item is not None for item in outcomes) == 1
    assert case.jobs.get(job.job_id).status in {JobStatus.COMPLETED, JobStatus.PAUSED}


def test_gpt_requires_valid_crc_and_geometry(tmp_path: Path) -> None:
    valid = tmp_path / "valid-gpt.img"
    _write_valid_gpt(valid)
    report = profile_storage(valid)
    assert report.partition_scheme == "GPT"
    assert len(report.partitions) == 1
    assert report.partitions[0].start_lba == 2048

    corrupt = tmp_path / "bad-gpt.img"
    data = bytearray(valid.read_bytes())
    data[512 + 40] ^= 0x01  # Change the header after CRC calculation.
    corrupt.write_bytes(data)
    bad = profile_storage(corrupt)
    assert bad.partition_scheme != "GPT"


def test_dhav_extension_metadata_and_bounded_stop(tmp_path: Path) -> None:
    frame = _dhav_extended_frame()
    source = tmp_path / "dhav.raw"
    source.write_bytes(frame)

    # A requested physical range cannot leak a record that ends outside it.
    assert scan_dhav_frames(source, stop=len(frame) - 1) == []

    records = scan_dhav_frames(source)
    assert len(records) == 1
    record = records[0]
    assert record.extension.video_codec == "hevc"
    assert record.extension.frame_rate == 15
    assert record.extension.width == 1280
    assert record.extension.height == 720
    assert record.codec_hint == "hevc"

    ext = parse_extension(bytes([0x81, 0x00, 0x08, 25]))
    assert ext.video_codec == "h264"
    assert ext.frame_rate == 25
