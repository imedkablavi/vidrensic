from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import os

from vidrensic.core.hashing import forensic_hashes
from vidrensic.plugins.wfs.codec import FRAGMENT_SIZE
from vidrensic.plugins.wfs.reconstruct import build_chains, extract_hevc


@dataclass(frozen=True)
class WFSRecoveredCandidate:
    candidate_id: str
    status: str
    reasons: tuple[str, ...]
    start_fragment: int
    fragments: tuple[int, ...]
    ambiguous_steps: int
    unresolved_steps: int
    native_output: Path
    native_bytes: int
    video_packets: int
    sha256: str
    sha512: str | None


def recover_segment(
    source: Path,
    starts: list[int] | tuple[int, ...],
    stop_fragment: int,
    output_dir: Path,
    *,
    label: str,
    data_offset: int = 0,
    fragment_size: int = FRAGMENT_SIZE,
    near: int = 32,
    far: int = 4096,
) -> tuple[list[WFSRecoveredCandidate], Path]:
    """Recover one simultaneous WFS recording boundary into native HEVC candidates.

    Outputs are deliberately neutral `candidate_XX` names. Physical camera
    identity is an analyst/correlation layer and is not inferred from slot order.
    """

    if not label or any(ch in label for ch in "/\\\x00"):
        raise ValueError("invalid segment label")
    if not starts:
        raise ValueError("at least one start fragment is required")

    source = source.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    fd = os.open(source, os.O_RDONLY)
    try:
        chains = build_chains(
            fd,
            starts,
            stop_fragment,
            near=near,
            far=far,
            data_offset=data_offset,
            fragment_size=fragment_size,
        )

        candidates: list[WFSRecoveredCandidate] = []
        for index, chain in enumerate(chains, start=1):
            candidate_id = f"candidate_{index:02d}"
            native = output_dir / f"{label}_{candidate_id}.hevc"
            extracted = extract_hevc(
                fd,
                chain.fragments,
                native,
                data_offset=data_offset,
                fragment_size=fragment_size,
            )
            hashes = forensic_hashes(native)

            reasons: list[str] = []
            if chain.ambiguous_steps:
                reasons.append(f"ambiguous continuation steps={chain.ambiguous_steps}")
            if chain.unresolved_steps:
                reasons.append(f"unresolved continuation steps={chain.unresolved_steps}")
            # Native extraction without decoder/timing QC can never be PASS.
            status = "REVIEW" if reasons else "UNKNOWN"

            candidates.append(
                WFSRecoveredCandidate(
                    candidate_id=candidate_id,
                    status=status,
                    reasons=tuple(reasons),
                    start_fragment=chain.start_fragment,
                    fragments=tuple(chain.fragments),
                    ambiguous_steps=chain.ambiguous_steps,
                    unresolved_steps=chain.unresolved_steps,
                    native_output=native,
                    native_bytes=extracted.hevc_bytes,
                    video_packets=extracted.video_packets,
                    sha256=hashes.sha256,
                    sha512=hashes.sha512,
                )
            )
    finally:
        os.close(fd)

    manifest_path = output_dir / f"{label}_recovery_manifest.json"
    payload = {
        "schema_version": 1,
        "plugin": "wfs",
        "source": str(source),
        "label": label,
        "data_offset": data_offset,
        "fragment_size": fragment_size,
        "starts": list(starts),
        "stop_fragment": stop_fragment,
        "near": near,
        "far": far,
        "candidates": [],
    }
    for candidate in candidates:
        record = asdict(candidate)
        record["native_output"] = str(candidate.native_output)
        record["fragments"] = list(candidate.fragments)
        record["reasons"] = list(candidate.reasons)
        payload["candidates"].append(record)

    temp = manifest_path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(manifest_path)
    return candidates, manifest_path
