from __future__ import annotations

import re


_SIZE_RE = re.compile(
    r"^\s*(?P<number>(?:0[xX][0-9a-fA-F]+)|(?:[0-9]+(?:\.[0-9]+)?))\s*(?P<unit>[A-Za-z]*)\s*$"
)

_DECIMAL = {
    "": 1,
    "b": 1,
    "kb": 1000,
    "mb": 1000**2,
    "gb": 1000**3,
    "tb": 1000**4,
    "pb": 1000**5,
}
_BINARY = {
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
    "pib": 1024**5,
}


def parse_byte_size(value: str) -> int:
    """Parse an integer/hex byte count or a decimal/binary size suffix.

    Examples: `4096`, `0x1000`, `64MiB`, `2.5GB`, `1TiB`.
    Fractional raw bytes and fractional hexadecimal values are not accepted.
    """

    match = _SIZE_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid byte size: {value!r}")
    number = match.group("number")
    unit = match.group("unit").casefold()
    if number.lower().startswith("0x"):
        if unit:
            raise ValueError("hexadecimal byte sizes cannot have a unit suffix")
        return int(number, 16)

    multiplier = _DECIMAL.get(unit)
    if multiplier is None:
        multiplier = _BINARY.get(unit)
    if multiplier is None:
        allowed = "B, KB, MB, GB, TB, PB, KiB, MiB, GiB, TiB, PiB"
        raise ValueError(f"unknown byte-size unit {unit!r}; use one of {allowed}")

    if "." not in number:
        return int(number) * multiplier
    if unit in {"", "b"}:
        raise ValueError("fractional raw bytes are not valid")
    whole, fraction = number.split(".", 1)
    numerator = int(whole + fraction)
    denominator = 10 ** len(fraction)
    scaled = numerator * multiplier
    if scaled % denominator:
        raise ValueError("size does not resolve to an exact whole number of bytes")
    return scaled // denominator
