from __future__ import annotations

from dataclasses import dataclass


WFS_FRAGMENT_SIZE = 2 * 1024 * 1024
KNOWN_RECORD_PREFIXES = (
    b"\x00\x00\x01\xfd",
    b"\x00\x00\x01\xfe",
    b"\x00\x00\x01\xfc",
    b"\x00\x00\x01\xfa",
    b"\x00\x00\x01\xf9",
)


@dataclass(frozen=True)
class WFSProfile:
    name: str = "wfs-0.5"
    fragment_size: int = WFS_FRAGMENT_SIZE
    fd_header_size: int = 16
    fe_header_size: int = 16
    short_header_size: int = 8

    def record_prefix_known(self, value: bytes) -> bool:
        return value[:4] in KNOWN_RECORD_PREFIXES
