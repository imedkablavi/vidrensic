from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import os

from vidrensic.core.hashing import forensic_hashes
from vidrensic.plugins.wfs.codec import FRAGMENT_SIZE
from vidrensic.plugins.wfs.reconstruct import build_chains, extract_video


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
    codec_hint: str | None
    codec_confidence: float
    trailing_unparsed_bytes: int
    sha256: str
    sha512: str | None


def _candidate_existing_paths(output_dir: Path, label: str, candidate_id: str) -> tuple[Path, ...]:
    stem = f"{label}_{candidate_id}"
    return tuple(output_dir / f"{stem}{suffix}" for suffix in (".video.es", ".es", ".h264", ".h265", ".hevc"))


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
    """Recover one simultaneous WFS recording boundary into native video candidates.

    Outputs are deliberately neutral `candidate_XX` names. Physical camera
    identity is an analyst/correlation layer and is not inferred from slot order.
    Codec naming is evidence-driven; unknown payloads remain `.es`.
    """

    if not label or any(ch in label for ch in "/\\\x00"):
        raise ValueError("invalid segment label")
    if not starts:
        raise ValueError("at least one start fragment is required")
    if data_offset < 0 or fragment_size <= 0:
        raise ValueError("data_offset and fragment_size must be valid")

    source = source.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / f"{label}_recovery_manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"recovery manifest already exists: {manifest_path}")

    fd = os.open(source, os.O_RDONLY)
    created_outputs: list[Path] = []
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
            existing = [path for path in _candidate_existing_paths(output_dir, label, candidate_id) if path.exists()]
            if existing:
                raise FileExistsError(f"candidate output already exists: {existing[0]}")

            temporary_native = output_dir / f"{label}_{candidate_id}.video.es"
            extracted = extract_video(
                fd,
                chain.fragments,
                temporary_native,
                data_offset=data_offset,
                fragment_size=fragment_size,
            )
            created_outputs.append(temporary_native)

            if extracted.codec_hint == "h264" and extracted.codec_confidence >= 0.80:
                native = output_dir / f"{label}_{candidate_id}.h264"
            elif extracted.codec_hint == "hevc" and extracted.codec_confidence >= 0.80:
                native = output_dir / f"{label}_{candidate_id}.h265"
            else:
                native = output_dir / f"{label}_{candidate_id}.es"
            if native != temporary_native:
                if native.exists():
                    raise FileExistsError(f"candidate output already exists: {native}")
                temporary_native.rename(native)
                created_outputs[-1] = native

            hashes = forensic_hashes(native)

            reasons: list[str] = []
            hard_fail = False
            if chain.ambiguous_steps:
                reasons.append(f"ambiguous continuation steps={chain.ambiguous_steps}")
            if chain.unresolved_steps:
                reasons.append(f"unresolved continuation steps={chain.unresolved_steps}")
            if extracted.video_packets == 0 or extracted.video_bytes == 0:
                reasons.append("no native video payload packets were extracted")
                hard_fail = True
            if extracted.trailing_unparsed_bytes:
                reasons.append(
                    f"incomplete/unparsed WFS tail bytes={extracted.trailing_unparsed_bytes}"
                )
            if extracted.codec_hint is None or extracted.codec_confidence < 0.80:
                reasons.append(
                    f"video codec is not established with high confidence ({extracted.codec_confidence:.2f})"
                )
                reasons.extend(extracted.codec_reasons[-2:])

            if hard_fail:
                status = "FAIL"
            elif reasons:
                status = "REVIEW"
            else:
                # Native extraction without complete decoder/timing QC can never be PASS.
                status = "UNKNOWN"

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
                    native_bytes=extracted.video_bytes,
                    video_packets=extracted.video_packets,
                    codec_hint=extracted.codec_hint,
                    codec_confidence=extracted.codec_confidence,
                    trailing_unparsed_bytes=extracted.trailing_unparsed_bytes,
                    sha256=hashes.sha256,
                    sha512=hashes.sha512,
                )
            )
    except Exception:
        # Partial artifacts are never silently presented as a completed recovery.
        # Keep bytes for forensic troubleshooting but mark them visibly.
        for path in created_outputs:
            if path.exists() and not path.name.endswith(".partial"):
                partial = path.with_name(path.name + ".partial")
                if not partial.exists():
                    path.rename(partial)
        raise
    finally:
        os.close(fd)

    payload = {
        "schema_version": 2,
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
        "forensic_notes": [
            "candidate IDs are reconstruction identities, not physical camera identities",
            "file extension is assigned only from codec parameter-set evidence; uncertain payloads remain .es",
            "native extraction alone never produces PASS status",
        ],
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
