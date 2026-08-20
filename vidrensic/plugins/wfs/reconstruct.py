from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import itertools
import os

from vidrensic.plugins.wfs.codec import (
    FRAGMENT_SIZE,
    VIDEO_TYPES,
    WFSParseError,
    packet_info,
    padding_here,
    parse_fragment_tail,
)


@dataclass
class WFSChain:
    start_fragment: int
    current_fragment: int
    fragments: list[int] = field(default_factory=list)
    tail: bytes | None = b""
    active: bool = True
    ambiguous_steps: int = 0
    unresolved_steps: int = 0
    candidate_counts: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class ExtractResult:
    output: Path
    hevc_bytes: int
    video_packets: int
    type_counts: dict[int, int]


def _pread(fd: int, size: int, offset: int) -> bytes:
    if size < 0 or offset < 0:
        raise ValueError("negative read parameters are invalid")
    return os.pread(fd, size, offset)


def _fragment_offset(data_offset: int, fragment: int, fragment_size: int) -> int:
    return data_offset + fragment * fragment_size


def init_chain(
    fd: int,
    start_fragment: int,
    *,
    data_offset: int = 0,
    fragment_size: int = FRAGMENT_SIZE,
) -> WFSChain:
    data = _pread(fd, fragment_size, _fragment_offset(data_offset, start_fragment, fragment_size))
    if len(data) != fragment_size:
        return WFSChain(
            start_fragment=start_fragment,
            current_fragment=start_fragment,
            fragments=[start_fragment],
            tail=None,
            active=False,
            unresolved_steps=1,
        )
    try:
        tail = parse_fragment_tail(data)
        unresolved = 0
    except WFSParseError:
        tail = b""
        unresolved = 1
    return WFSChain(
        start_fragment=start_fragment,
        current_fragment=start_fragment,
        fragments=[start_fragment],
        tail=tail,
        active=tail is not None,
        unresolved_steps=unresolved,
    )


def probe_candidate(
    fd: int,
    tail: bytes | None,
    fragment: int,
    *,
    data_offset: int = 0,
    fragment_size: int = FRAGMENT_SIZE,
) -> tuple[bool, bytes | None]:
    if tail is None:
        return False, None

    offset = _fragment_offset(data_offset, fragment, fragment_size)
    probe = _pread(fd, 512, offset)
    if not probe:
        return False, None

    if tail == b"":
        if not padding_here(probe, 0) and packet_info(probe, 0) is None:
            return False, None
    else:
        head = tail + probe
        info = packet_info(head, 0)
        if info is None:
            return False, None
        need = info.total_size - len(tail)
        if need < 0 or need >= fragment_size - 32:
            return False, None
        continuation = _pread(fd, need + 512, offset)
        if len(continuation) < need:
            return False, None
        if not padding_here(continuation, need) and packet_info(continuation, need) is None:
            return False, None

    data = _pread(fd, fragment_size, offset)
    if len(data) != fragment_size:
        return False, None
    try:
        new_tail = parse_fragment_tail((tail or b"") + data)
    except WFSParseError:
        return False, None
    return True, new_tail


def candidate_list(
    fd: int,
    state: WFSChain,
    used: set[int],
    stop_fragment: int,
    *,
    near: int,
    far: int,
    top: int = 6,
    data_offset: int = 0,
    fragment_size: int = FRAGMENT_SIZE,
) -> list[tuple[float, int, bytes | None]]:
    first = state.current_fragment + 1

    def collect(start: int, stop: int) -> list[tuple[float, int, bytes | None]]:
        found: list[tuple[float, int, bytes | None]] = []
        for fragment in range(start, stop):
            if fragment in used:
                continue
            ok, new_tail = probe_candidate(
                fd,
                state.tail,
                fragment,
                data_offset=data_offset,
                fragment_size=fragment_size,
            )
            if not ok:
                continue
            gap = fragment - state.current_fragment
            score = float(gap)
            if new_tail is None:
                score -= 0.25
            found.append((score, fragment, new_tail))
        found.sort(key=lambda item: (item[0], item[1]))
        return found[:top]

    near_end = min(stop_fragment, first + near)
    found = collect(first, near_end)
    if found:
        return found

    far_end = min(stop_fragment, first + far)
    if far_end <= near_end:
        return []
    return collect(near_end, far_end)


def build_chains(
    fd: int,
    starts: list[int] | tuple[int, ...],
    stop_fragment: int,
    *,
    near: int = 32,
    far: int = 4096,
    candidate_top: int = 6,
    max_iterations: int = 10000,
    data_offset: int = 0,
    fragment_size: int = FRAGMENT_SIZE,
) -> list[WFSChain]:
    """Conservatively reconstruct simultaneous WFS fragment chains.

    Candidate continuations are structurally validated before distance affects
    ranking. Streams advance jointly and a physical fragment may not be assigned
    to two streams in the same reconstruction. Multiple valid continuations are
    preserved as ambiguity evidence.

    This is a bounded local optimizer, not the planned global graph solver.
    """

    if not starts:
        return []
    if len(set(starts)) != len(starts):
        raise ValueError("duplicate start fragments are invalid")
    if any(fragment < 0 for fragment in starts):
        raise ValueError("start fragments cannot be negative")
    if stop_fragment <= max(starts):
        raise ValueError("stop_fragment must follow all start fragments")
    if near <= 0 or far < near:
        raise ValueError("require 0 < near <= far")

    states = [
        init_chain(
            fd,
            fragment,
            data_offset=data_offset,
            fragment_size=fragment_size,
        )
        for fragment in sorted(starts)
    ]
    used = set(starts)

    for _ in range(max_iterations):
        active = [index for index, state in enumerate(states) if state.active]
        if not active:
            break

        options = {
            index: candidate_list(
                fd,
                states[index],
                used,
                stop_fragment,
                near=near,
                far=far,
                top=candidate_top,
                data_offset=data_offset,
                fragment_size=fragment_size,
            )
            for index in active
        }

        for index in active:
            count = len(options[index])
            states[index].candidate_counts.append(count)
            if count > 1:
                states[index].ambiguous_steps += 1

        choice_lists: list[list[tuple[float, int | None, bytes | None]]] = []
        for index in active:
            per: list[tuple[float, int | None, bytes | None]] = list(options[index])
            per.append((1_000_000.0, None, None))
            choice_lists.append(per)

        best: tuple[float, tuple[tuple[float, int | None, bytes | None], ...]] | None = None
        for combo in itertools.product(*choice_lists):
            assigned = [item[1] for item in combo if item[1] is not None]
            if len(assigned) != len(set(assigned)):
                continue
            score = sum(item[0] for item in combo)
            score += 10_000_000.0 * sum(item[1] is None for item in combo)
            if best is None or score < best[0]:
                best = (score, combo)

        progressed = False
        for position, index in enumerate(active):
            state = states[index]
            if best is None:
                state.active = False
                state.unresolved_steps += 1
                continue

            _, fragment, new_tail = best[1][position]
            if fragment is None:
                state.active = False
                state.unresolved_steps += 1
                continue

            state.fragments.append(fragment)
            state.current_fragment = fragment
            state.tail = new_tail
            used.add(fragment)
            progressed = True
            if new_tail is None:
                state.active = False

        if not progressed:
            break
    else:
        for state in states:
            if state.active:
                state.active = False
                state.unresolved_steps += 1

    return states


def extract_hevc(
    fd: int,
    fragments: list[int] | tuple[int, ...],
    output: Path,
    *,
    data_offset: int = 0,
    fragment_size: int = FRAGMENT_SIZE,
) -> ExtractResult:
    """Extract native video-bearing WFS payloads into an HEVC elementary stream."""

    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    buffer = b""
    written = 0
    packets = 0
    type_counts: dict[int, int] = {}

    with output.open("wb") as target:
        for fragment in fragments:
            data = _pread(
                fd,
                fragment_size,
                _fragment_offset(data_offset, fragment, fragment_size),
            )
            if len(data) != fragment_size:
                raise WFSParseError(f"short read for WFS fragment {fragment}")
            buffer += data
            offset = 0

            while offset < len(buffer):
                if padding_here(buffer, offset):
                    offset = len(buffer)
                    break
                info = packet_info(buffer, offset)
                if info is None:
                    if len(buffer) - offset < 16:
                        break
                    raise WFSParseError(
                        f"extract sync lost fragment={fragment} offset=0x{offset:X}"
                    )
                end = offset + info.total_size
                if end > len(buffer):
                    break

                type_counts[info.packet_type] = type_counts.get(info.packet_type, 0) + 1
                if info.packet_type in VIDEO_TYPES:
                    payload_start = offset + info.header_size
                    payload = buffer[payload_start:end]
                    target.write(payload)
                    written += len(payload)
                    packets += 1
                offset = end

            buffer = buffer[offset:]
            if len(buffer) > 8 * 1024 * 1024:
                raise WFSParseError("WFS extraction carry buffer exceeded safety limit")

    return ExtractResult(
        output=output,
        hevc_bytes=written,
        video_packets=packets,
        type_counts=type_counts,
    )
