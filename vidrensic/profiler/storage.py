from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json
import os
import struct
import uuid

from vidrensic.acquisition.linux import require_safe_source


@dataclass(frozen=True)
class PartitionRecord:
    scheme: str
    index: int
    start_lba: int
    end_lba: int
    sector_size: int
    type_id: str
    unique_id: str | None = None
    name: str | None = None
    bootable: bool = False

    @property
    def start_bytes(self) -> int:
        return self.start_lba * self.sector_size

    @property
    def size_bytes(self) -> int:
        if self.end_lba < self.start_lba:
            return 0
        return (self.end_lba - self.start_lba + 1) * self.sector_size


@dataclass(frozen=True)
class FilesystemHit:
    offset: int
    family: str
    confidence: float
    evidence: tuple[str, ...]
    partition_index: int | None = None


@dataclass(frozen=True)
class StorageReport:
    source: Path
    size_bytes: int
    partition_scheme: str | None
    sector_size: int
    partitions: tuple[PartitionRecord, ...]
    filesystems: tuple[FilesystemHit, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source": str(self.source),
            "size_bytes": self.size_bytes,
            "partition_scheme": self.partition_scheme,
            "sector_size": self.sector_size,
            "partitions": [
                {
                    **asdict(item),
                    "start_bytes": item.start_bytes,
                    "size_bytes": item.size_bytes,
                }
                for item in self.partitions
            ],
            "filesystems": [asdict(item) for item in self.filesystems],
            "notes": list(self.notes),
        }

    def write_json(self, output: Path) -> Path:
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_suffix(output.suffix + ".tmp")
        temp.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(output)
        return output


def _pread(fd: int, size: int, offset: int) -> bytes:
    if offset < 0 or size < 0:
        return b""
    return os.pread(fd, size, offset)


def _parse_mbr(sector: bytes, sector_size: int) -> tuple[list[PartitionRecord], bool]:
    if len(sector) < 512 or sector[510:512] != b"\x55\xaa":
        return [], False
    partitions: list[PartitionRecord] = []
    protective_gpt = False
    for index in range(4):
        entry = sector[446 + index * 16 : 446 + (index + 1) * 16]
        if len(entry) != 16:
            continue
        boot = entry[0] == 0x80
        type_code = entry[4]
        start_lba = struct.unpack_from("<I", entry, 8)[0]
        sectors = struct.unpack_from("<I", entry, 12)[0]
        if type_code == 0 or sectors == 0:
            continue
        if type_code == 0xEE:
            protective_gpt = True
        partitions.append(
            PartitionRecord(
                scheme="MBR",
                index=index + 1,
                start_lba=start_lba,
                end_lba=start_lba + sectors - 1,
                sector_size=sector_size,
                type_id=f"0x{type_code:02X}",
                bootable=boot,
            )
        )
    return partitions, protective_gpt


def _guid_text(raw: bytes) -> str:
    try:
        return str(uuid.UUID(bytes_le=raw))
    except (ValueError, AttributeError):
        return raw.hex()


def _parse_gpt(fd: int, source_size: int) -> tuple[int, list[PartitionRecord]] | None:
    for sector_size in (512, 4096):
        header = _pread(fd, sector_size, sector_size)
        if len(header) < 92 or header[:8] != b"EFI PART":
            continue
        header_size = struct.unpack_from("<I", header, 12)[0]
        if not 92 <= header_size <= sector_size:
            continue
        entry_lba = struct.unpack_from("<Q", header, 72)[0]
        count = struct.unpack_from("<I", header, 80)[0]
        entry_size = struct.unpack_from("<I", header, 84)[0]
        if not 128 <= entry_size <= 4096 or not 1 <= count <= 4096:
            continue
        total = count * entry_size
        if total > 16 * 1024 * 1024:
            continue
        table_offset = entry_lba * sector_size
        if table_offset + total > source_size:
            continue
        table = _pread(fd, total, table_offset)
        if len(table) != total:
            continue
        partitions: list[PartitionRecord] = []
        for index in range(count):
            entry = table[index * entry_size : (index + 1) * entry_size]
            type_guid = entry[:16]
            if type_guid == b"\x00" * 16:
                continue
            unique_guid = entry[16:32]
            first_lba = struct.unpack_from("<Q", entry, 32)[0]
            last_lba = struct.unpack_from("<Q", entry, 40)[0]
            if first_lba == 0 or last_lba < first_lba:
                continue
            name_raw = entry[56 : min(entry_size, 128)]
            try:
                name = name_raw.decode("utf-16le", errors="ignore").split("\x00", 1)[0] or None
            except UnicodeError:
                name = None
            partitions.append(
                PartitionRecord(
                    scheme="GPT",
                    index=index + 1,
                    start_lba=first_lba,
                    end_lba=last_lba,
                    sector_size=sector_size,
                    type_id=_guid_text(type_guid),
                    unique_id=_guid_text(unique_guid),
                    name=name,
                )
            )
        return sector_size, partitions
    return None


def _probe_filesystem(fd: int, base: int, partition_index: int | None) -> list[FilesystemHit]:
    hits: list[FilesystemHit] = []

    boot = _pread(fd, 512, base)
    if boot[:4] == b"XFSB":
        hits.append(FilesystemHit(base, "XFS", 0.99, ("XFSB superblock magic",), partition_index))
    if boot[3:11] == b"NTFS    ":
        hits.append(FilesystemHit(base, "NTFS", 0.99, ("NTFS boot-sector OEM ID",), partition_index))
    if boot[3:11] == b"EXFAT   ":
        hits.append(FilesystemHit(base, "exFAT", 0.99, ("EXFAT boot-sector OEM ID",), partition_index))
    fat16 = boot[54:62].rstrip(b" \x00")
    fat32 = boot[82:90].rstrip(b" \x00")
    if fat16 in (b"FAT12", b"FAT16"):
        hits.append(FilesystemHit(base, fat16.decode(), 0.95, ("FAT boot-sector type label",), partition_index))
    if fat32 == b"FAT32":
        hits.append(FilesystemHit(base, "FAT32", 0.95, ("FAT32 boot-sector type label",), partition_index))

    ext = _pread(fd, 2, base + 1024 + 56)
    if ext == b"\x53\xef":
        hits.append(
            FilesystemHit(
                base,
                "EXT2/3/4 family",
                0.98,
                ("EXT superblock magic 0xEF53 at +1080",),
                partition_index,
            )
        )

    jfs = _pread(fd, 4, base + 0x8000)
    if jfs == b"JFS1":
        hits.append(FilesystemHit(base, "JFS", 0.99, ("JFS1 superblock magic",), partition_index))

    btrfs = _pread(fd, 8, base + 0x10000 + 0x40)
    if btrfs == b"_BHRfS_M":
        hits.append(FilesystemHit(base, "Btrfs", 0.99, ("Btrfs superblock magic",), partition_index))

    hfs = _pread(fd, 2, base + 1024)
    if hfs in (b"H+", b"HX"):
        hits.append(FilesystemHit(base, "HFS+", 0.95, ("HFS+ volume-header signature",), partition_index))

    return hits


def profile_storage(source: Path) -> StorageReport:
    """Map common partition tables and known filesystems without mounting them."""

    info = require_safe_source(source)
    fd = os.open(info.path, os.O_RDONLY)
    try:
        first = _pread(fd, 4096, 0)
        mbr, protective = _parse_mbr(first[:512], 512)
        gpt = _parse_gpt(fd, info.size_bytes)
        if gpt is not None:
            sector_size, partitions = gpt
            scheme = "GPT"
        elif mbr:
            sector_size = 512
            partitions = mbr
            scheme = "MBR"
        else:
            sector_size = 512
            partitions = []
            scheme = None

        filesystems: list[FilesystemHit] = []
        # Always inspect byte zero: DVR images are frequently unpartitioned or
        # use filesystem-like structures without a conventional partition table.
        filesystems.extend(_probe_filesystem(fd, 0, None))
        for part in partitions:
            if part.start_bytes >= info.size_bytes:
                continue
            filesystems.extend(_probe_filesystem(fd, part.start_bytes, part.index))
    finally:
        os.close(fd)

    notes = [
        "known-filesystem detection does not imply that surveillance video is stored as ordinary files",
        "proprietary video areas can coexist with EXT/XFS/JFS/FAT metadata partitions or unpartitioned space",
        "no filesystem was mounted or repaired",
    ]
    if protective and scheme != "GPT":
        notes.append("protective MBR observed but a valid GPT header/table was not parsed")
    if not partitions:
        notes.append("no conventional MBR/GPT partition entries were identified")

    return StorageReport(
        source=info.path,
        size_bytes=info.size_bytes,
        partition_scheme=scheme,
        sector_size=sector_size,
        partitions=tuple(partitions),
        filesystems=tuple(filesystems),
        notes=tuple(notes),
    )
