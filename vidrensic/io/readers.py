from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable
import os

from vidrensic.acquisition.linux import SourceInfo, require_safe_source


@runtime_checkable
class RandomAccessReader(Protocol):
    @property
    def size(self) -> int: ...

    def read_at(self, offset: int, size: int) -> bytes: ...

    def close(self) -> None: ...

    def describe(self) -> dict: ...


class FileReader:
    """Read-only random-access reader for one evidence file/block device."""

    def __init__(self, path: Path):
        self.info: SourceInfo = require_safe_source(path)
        self._fd = os.open(self.info.path, os.O_RDONLY)
        self._closed = False

    @property
    def size(self) -> int:
        return self.info.size_bytes

    def read_at(self, offset: int, size: int) -> bytes:
        if self._closed:
            raise ValueError("reader is closed")
        if offset < 0 or size < 0:
            raise ValueError("offset and size cannot be negative")
        if offset >= self.size or size == 0:
            return b""
        return os.pread(self._fd, min(size, self.size - offset), offset)

    def close(self) -> None:
        if not self._closed:
            os.close(self._fd)
            self._closed = True

    def describe(self) -> dict:
        return {
            "type": "file",
            "path": str(self.info.path),
            "size": self.size,
            "is_block_device": self.info.is_block_device,
            "read_only": self.info.read_only,
        }

    def __enter__(self) -> FileReader:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class ConcatReader:
    """Logical concatenation/JBOD reader over read-only evidence members."""

    def __init__(self, members: tuple[RandomAccessReader, ...]):
        if not members:
            raise ValueError("at least one member is required")
        if any(member.size <= 0 for member in members):
            raise ValueError("all members must have positive size")
        self.members = members
        cumulative = []
        total = 0
        for member in members:
            total += member.size
            cumulative.append(total)
        self._ends = tuple(cumulative)
        self._size = total
        self._closed = False

    @property
    def size(self) -> int:
        return self._size

    def read_at(self, offset: int, size: int) -> bytes:
        if self._closed:
            raise ValueError("reader is closed")
        if offset < 0 or size < 0:
            raise ValueError("offset and size cannot be negative")
        if offset >= self.size or size == 0:
            return b""
        remaining = min(size, self.size - offset)
        result = bytearray()
        logical = offset
        while remaining:
            index = bisect_right(self._ends, logical)
            previous_end = 0 if index == 0 else self._ends[index - 1]
            member = self.members[index]
            member_offset = logical - previous_end
            take = min(remaining, member.size - member_offset)
            chunk = member.read_at(member_offset, take)
            if len(chunk) != take:
                break
            result += chunk
            logical += take
            remaining -= take
        return bytes(result)

    def close(self) -> None:
        if self._closed:
            return
        errors = []
        for member in self.members:
            try:
                member.close()
            except Exception as exc:  # best-effort cleanup of every member
                errors.append(exc)
        self._closed = True
        if errors:
            raise errors[0]

    def describe(self) -> dict:
        return {
            "type": "concat-jbod",
            "size": self.size,
            "member_count": len(self.members),
            "members": [member.describe() for member in self.members],
        }

    def __enter__(self) -> ConcatReader:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


@dataclass(frozen=True)
class StripeMapping:
    logical_offset: int
    member_index: int
    member_offset: int
    contiguous_bytes: int


class StripeReader:
    """RAID0-style rotating stripe reader.

    This implements only deterministic data placement. It does not infer member
    order, stripe size, missing members, metadata offsets, or parity. Those are
    forensic hypotheses that must be supplied/validated separately.
    """

    def __init__(
        self,
        members: tuple[RandomAccessReader, ...],
        *,
        stripe_size: int,
        member_data_offset: int = 0,
    ):
        if len(members) < 2:
            raise ValueError("RAID0 requires at least two members")
        if stripe_size < 512 or stripe_size & (stripe_size - 1):
            raise ValueError("stripe_size must be a power of two >= 512")
        if member_data_offset < 0:
            raise ValueError("member_data_offset cannot be negative")
        available = [member.size - member_data_offset for member in members]
        if any(value <= 0 for value in available):
            raise ValueError("member_data_offset leaves an empty member")
        # RAID0 logical space can only safely use complete equal stripe counts
        # from every member. Unequal tails are excluded rather than guessed.
        stripes_per_member = min(value // stripe_size for value in available)
        if stripes_per_member <= 0:
            raise ValueError("members do not contain one complete stripe")
        self.members = members
        self.stripe_size = stripe_size
        self.member_data_offset = member_data_offset
        self.stripes_per_member = stripes_per_member
        self._size = stripes_per_member * stripe_size * len(members)
        self._closed = False

    @property
    def size(self) -> int:
        return self._size

    def map_offset(self, logical_offset: int) -> StripeMapping:
        if logical_offset < 0 or logical_offset >= self.size:
            raise ValueError("logical offset is outside RAID0 range")
        stripe_number, within = divmod(logical_offset, self.stripe_size)
        member_index = stripe_number % len(self.members)
        member_stripe = stripe_number // len(self.members)
        member_offset = self.member_data_offset + member_stripe * self.stripe_size + within
        return StripeMapping(
            logical_offset=logical_offset,
            member_index=member_index,
            member_offset=member_offset,
            contiguous_bytes=self.stripe_size - within,
        )

    def read_at(self, offset: int, size: int) -> bytes:
        if self._closed:
            raise ValueError("reader is closed")
        if offset < 0 or size < 0:
            raise ValueError("offset and size cannot be negative")
        if offset >= self.size or size == 0:
            return b""
        remaining = min(size, self.size - offset)
        logical = offset
        result = bytearray()
        while remaining:
            mapping = self.map_offset(logical)
            take = min(remaining, mapping.contiguous_bytes)
            chunk = self.members[mapping.member_index].read_at(mapping.member_offset, take)
            if len(chunk) != take:
                break
            result += chunk
            logical += take
            remaining -= take
        return bytes(result)

    def close(self) -> None:
        if self._closed:
            return
        errors = []
        for member in self.members:
            try:
                member.close()
            except Exception as exc:
                errors.append(exc)
        self._closed = True
        if errors:
            raise errors[0]

    def describe(self) -> dict:
        return {
            "type": "raid0-stripe",
            "size": self.size,
            "member_count": len(self.members),
            "stripe_size": self.stripe_size,
            "member_data_offset": self.member_data_offset,
            "stripes_per_member": self.stripes_per_member,
            "members": [member.describe() for member in self.members],
            "forensic_note": "member order/stripe size are supplied hypotheses, not auto-detected facts",
        }

    def __enter__(self) -> StripeReader:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def open_file_members(paths: tuple[Path, ...]) -> tuple[FileReader, ...]:
    readers: list[FileReader] = []
    try:
        for path in paths:
            readers.append(FileReader(path))
    except Exception:
        for reader in readers:
            reader.close()
        raise
    return tuple(readers)
