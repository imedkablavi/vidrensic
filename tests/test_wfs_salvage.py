from __future__ import annotations

import pytest

from vidrensic.plugins.wfs.salvage import scan_bounded_annexb_units


def test_h264_salvage_emits_only_bounded_units_and_marks_idr() -> None:
    data = (
        b"corrupt-prefix"
        b"\x00\x00\x00\x01\x67\x64\x00\x1f"
        b"\x00\x00\x01\x68\xee\x3c\x80"
        b"\x00\x00\x00\x01\x65\x88\x84\x21"
        b"\x00\x00\x01\x41\x9a\x22"
    )
    result = scan_bounded_annexb_units(data, base_offset=4096)

    assert result.codec_hint == "h264"
    assert result.codec_confidence >= 0.80
    # Four starts yield three provably bounded units. The final candidate is
    # intentionally discarded because no later start code proves its end.
    assert len(result.units) == 3
    assert result.units[0].parameter_set is True
    assert result.units[1].parameter_set is True
    assert result.units[2].random_access is True
    assert result.random_access_units == 1
    assert result.units[0].offset >= 4096
    assert result.discarded_unbounded_tail_bytes > 0


def test_uncertain_annexb_does_not_invent_codec_or_gop_labels() -> None:
    data = b"\x00\x00\x01\x01abc\x00\x00\x01\x02def\x00\x00\x01\x03tail"
    result = scan_bounded_annexb_units(data)

    assert len(result.units) == 2
    assert result.codec_hint is None
    assert all(item.codec is None for item in result.units)
    assert all(item.nal_type is None for item in result.units)
    assert result.random_access_units == 0


def test_salvage_rejects_invalid_bounds() -> None:
    with pytest.raises(ValueError, match="base_offset"):
        scan_bounded_annexb_units(b"", base_offset=-1)
    with pytest.raises(ValueError, match="max_units"):
        scan_bounded_annexb_units(b"", max_units=0)


def test_salvage_unit_limit_is_explicitly_incomplete() -> None:
    data = b"".join(b"\x00\x00\x01\x01x" for _ in range(8))
    result = scan_bounded_annexb_units(data, max_units=2)
    assert len(result.units) == 2
    assert any("max_units" in note for note in result.notes)
