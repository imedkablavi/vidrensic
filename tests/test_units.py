from __future__ import annotations

import pytest

from vidrensic.core.units import parse_byte_size


def test_parse_byte_size_integer_hex_decimal_and_binary() -> None:
    assert parse_byte_size("4096") == 4096
    assert parse_byte_size("0x1000") == 4096
    assert parse_byte_size("64MiB") == 64 * 1024**2
    assert parse_byte_size("2GB") == 2_000_000_000
    assert parse_byte_size("1.5GiB") == 3 * 1024**3 // 2
    assert parse_byte_size("1 TB") == 1_000_000_000_000


def test_parse_byte_size_rejects_ambiguous_or_fractional_bytes() -> None:
    with pytest.raises(ValueError):
        parse_byte_size("1.5")
    with pytest.raises(ValueError):
        parse_byte_size("0x1000MiB")
    with pytest.raises(ValueError):
        parse_byte_size("12XB")
