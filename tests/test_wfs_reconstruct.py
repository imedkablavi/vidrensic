from __future__ import annotations

from pathlib import Path
import os
import struct

import pytest

from vidrensic.plugins.wfs.codec import WFSParseError
from vidrensic.plugins.wfs.reconstruct import (
    WFSChain,
    build_chains,
    candidate_list,
    extract_video,
    init_chain,
    probe_candidate,
)


FRAG = 128


def _fc(payload: bytes, *, declared: int | None = None) -> bytes:
    size = len(payload) if declared is None else declared
    return b"\x00\x00\x01\xfc" + struct.pack("<I", size) + payload


def _write_fragments(path: Path, fragments: list[bytes]) -> None:
    with path.open("wb") as fh:
        for fragment in fragments:
            assert len(fragment) == FRAG
            fh.write(fragment)


def _terminal_packet(payload: bytes = b"video") -> bytes:
    packet = _fc(payload)
    return packet + bytes(FRAG - len(packet))


def _carry_fragment() -> bytes:
    # FC total size is 208 bytes. A 128-byte first fragment therefore carries
    # 80 bytes into the next physical fragment.
    packet_prefix = _fc(b"A" * (FRAG - 8), declared=200)
    assert len(packet_prefix) == FRAG
    return packet_prefix


def _valid_continuation() -> bytes:
    return b"B" * 80 + bytes(FRAG - 80)


def _invalid_continuation() -> bytes:
    return b"B" * 80 + b"not-a-wfs-boundary" + b"X" * (FRAG - 80 - 18)


def test_init_chain_terminal_padding_and_short_read(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(_terminal_packet())
    fd = os.open(source, os.O_RDONLY)
    try:
        terminal = init_chain(fd, 0, fragment_size=FRAG)
        short = init_chain(fd, 1, fragment_size=FRAG)
    finally:
        os.close(fd)
    assert terminal.active is False
    assert terminal.tail is None
    assert terminal.unresolved_steps == 0
    assert short.active is False
    assert short.tail is None
    assert short.unresolved_steps == 1


def test_probe_candidate_validates_carry_boundary(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    _write_fragments(source, [_carry_fragment(), _valid_continuation(), _invalid_continuation()])
    fd = os.open(source, os.O_RDONLY)
    try:
        chain = init_chain(fd, 0, fragment_size=FRAG)
        ok, new_tail = probe_candidate(fd, chain.tail, 1, fragment_size=FRAG)
        bad, _ = probe_candidate(fd, chain.tail, 2, fragment_size=FRAG)
        impossible, _ = probe_candidate(fd, None, 1, fragment_size=FRAG)
    finally:
        os.close(fd)
    assert chain.active is True
    assert chain.tail
    assert ok is True
    assert new_tail is None
    assert bad is False
    assert impossible is False


def test_candidate_list_falls_back_from_near_to_far(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    _write_fragments(source, [_carry_fragment(), _invalid_continuation(), _valid_continuation()])
    fd = os.open(source, os.O_RDONLY)
    try:
        chain = init_chain(fd, 0, fragment_size=FRAG)
        found = candidate_list(
            fd,
            chain,
            {0},
            3,
            near=1,
            far=3,
            top=4,
            fragment_size=FRAG,
        )
    finally:
        os.close(fd)
    assert len(found) == 1
    assert found[0][1] == 2
    assert found[0][2] is None


def test_local_build_chains_uses_structural_far_candidate(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    _write_fragments(source, [_carry_fragment(), _invalid_continuation(), _valid_continuation()])
    fd = os.open(source, os.O_RDONLY)
    try:
        chains = build_chains(
            fd,
            [0],
            3,
            near=1,
            far=3,
            fragment_size=FRAG,
        )
    finally:
        os.close(fd)
    assert chains[0].fragments == [0, 2]
    assert chains[0].candidate_counts == [1]
    assert chains[0].unresolved_steps == 0
    assert chains[0].active is False


def test_local_build_chains_marks_unresolved_when_no_candidate(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    _write_fragments(source, [_carry_fragment(), _invalid_continuation()])
    fd = os.open(source, os.O_RDONLY)
    try:
        chains = build_chains(
            fd,
            [0],
            2,
            near=1,
            far=2,
            fragment_size=FRAG,
        )
    finally:
        os.close(fd)
    assert chains[0].fragments == [0]
    assert chains[0].unresolved_steps == 1
    assert chains[0].candidate_counts == [0]


def test_extract_video_rejects_duplicate_negative_and_short_fragment(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(_terminal_packet())
    fd = os.open(source, os.O_RDONLY)
    try:
        with pytest.raises(ValueError, match="duplicate"):
            extract_video(fd, [0, 0], tmp_path / "dup.es", fragment_size=FRAG)
        with pytest.raises(ValueError, match="negative"):
            extract_video(fd, [-1], tmp_path / "neg.es", fragment_size=FRAG)
        with pytest.raises(WFSParseError, match="short read"):
            extract_video(fd, [1], tmp_path / "short.es", fragment_size=FRAG)
    finally:
        os.close(fd)


def test_extract_video_detects_structural_sync_loss(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"Z" * FRAG)
    fd = os.open(source, os.O_RDONLY)
    try:
        with pytest.raises(WFSParseError, match="sync lost"):
            extract_video(fd, [0], tmp_path / "bad.es", fragment_size=FRAG)
    finally:
        os.close(fd)


@pytest.mark.parametrize(
    "starts,stop,kwargs",
    [
        ([1, 1], 3, {}),
        ([-1], 3, {}),
        ([2], 2, {}),
        ([0], 2, {"near": 0}),
        ([0], 2, {"candidate_top": 0}),
        ([0], 2, {"max_iterations": 0}),
    ],
)
def test_local_builder_rejects_invalid_parameters(tmp_path: Path, starts, stop, kwargs) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(bytes(FRAG * 3))
    fd = os.open(source, os.O_RDONLY)
    try:
        with pytest.raises(ValueError):
            build_chains(fd, starts, stop, fragment_size=FRAG, **kwargs)
    finally:
        os.close(fd)


def test_candidate_list_respects_used_fragments(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    _write_fragments(source, [_carry_fragment(), _valid_continuation()])
    fd = os.open(source, os.O_RDONLY)
    try:
        state = WFSChain(0, 0, [0], _carry_fragment(), True)
        # Use the real parsed tail instead of the synthetic full fragment.
        state.tail = init_chain(fd, 0, fragment_size=FRAG).tail
        found = candidate_list(
            fd,
            state,
            {0, 1},
            2,
            near=1,
            far=2,
            fragment_size=FRAG,
        )
    finally:
        os.close(fd)
    assert found == []
