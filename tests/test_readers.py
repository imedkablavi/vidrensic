from __future__ import annotations

from pathlib import Path

from vidrensic.io import ConcatReader, FileReader, StripeReader, open_file_members


def test_concat_reader_crosses_member_boundary(tmp_path: Path) -> None:
    first = tmp_path / "disk1.img"
    second = tmp_path / "disk2.img"
    first.write_bytes(b"A" * 16)
    second.write_bytes(b"B" * 16)
    members = open_file_members((first, second))
    with ConcatReader(members) as reader:
        assert reader.size == 32
        assert reader.read_at(12, 8) == b"AAAA" + b"BBBB"
        assert reader.describe()["type"] == "concat-jbod"


def test_raid0_reader_maps_rotating_stripes(tmp_path: Path) -> None:
    first = tmp_path / "disk1.img"
    second = tmp_path / "disk2.img"
    # 512-byte stripes. Member 0 holds logical stripes 0/2; member 1 holds 1/3.
    first.write_bytes(b"A" * 512 + b"C" * 512)
    second.write_bytes(b"B" * 512 + b"D" * 512)
    members = open_file_members((first, second))
    with StripeReader(members, stripe_size=512) as reader:
        assert reader.size == 2048
        assert reader.read_at(0, 2048) == (
            b"A" * 512 + b"B" * 512 + b"C" * 512 + b"D" * 512
        )
        mapping = reader.map_offset(512 + 7)
        assert mapping.member_index == 1
        assert mapping.member_offset == 7
        assert mapping.contiguous_bytes == 505


def test_raid0_excludes_unequal_member_tail(tmp_path: Path) -> None:
    first = tmp_path / "disk1.img"
    second = tmp_path / "disk2.img"
    first.write_bytes(b"A" * 1536)
    second.write_bytes(b"B" * 1024)
    members = (FileReader(first), FileReader(second))
    with StripeReader(members, stripe_size=512) as reader:
        # Two complete stripes per member = four logical stripes.
        assert reader.size == 2048
