from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import struct


def _packed_time(year: int, month: int, day: int, hour: int, minute: int, second: int) -> int:
    return (
        ((year - 2000) & 0x3F) << 26
        | (month & 0x0F) << 22
        | (day & 0x1F) << 17
        | (hour & 0x1F) << 12
        | (minute & 0x3F) << 6
        | (second & 0x3F)
    )


def _dhav_frame(channel: int, frame_number: int, second: int) -> bytes:
    # Deliberately tiny synthetic Annex-B H.264-looking payload. It is parser
    # evidence, not a playable CCTV recording.
    payload = b"\x00\x00\x00\x01\x67" + bytes([0x40 + channel]) * 32
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


def build_demo_bytes() -> bytes:
    data = bytearray(b"VIDRENSIC-SYNTHETIC-DEMO\x00")
    data.extend(b"X" * 97)
    frame_number = {0: 1, 1: 100}

    for second in range(12):
        channel = second % 2
        data.extend(_dhav_frame(channel, frame_number[channel], second))
        frame_number[channel] += 1
        if second in {2, 6, 9}:
            data.extend(b"synthetic-noise")

    return bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic, non-video DHAV parser demo fixture."
    )
    parser.add_argument("--out", type=Path, default=Path(".vidrensic-demo/synthetic-dhav.raw"))
    args = parser.parse_args()

    output = args.out.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_demo_bytes()
    output.write_bytes(payload)

    print(f"source={output}")
    print("frames=12")
    print("channels=2")
    print(f"bytes={len(payload)}")
    print(f"sha256={hashlib.sha256(payload).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
