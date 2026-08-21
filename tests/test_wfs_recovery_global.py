from __future__ import annotations

from pathlib import Path
import json

import pytest

import vidrensic.plugins.wfs.recovery as recovery
from vidrensic.plugins.wfs.global_reconstruct import WFSGlobalSolution, WFSPathHypothesis
from vidrensic.plugins.wfs.reconstruct import ExtractResult, WFSChain


def _solution(*, truncated: bool = False, margin: float | None = None) -> WFSGlobalSolution:
    hypothesis = WFSPathHypothesis(
        start_fragment=0,
        fragments=(0,),
        total_cost=0.0,
        ambiguous_steps=0,
        unresolved_steps=0,
        candidate_counts=(),
        terminal_reason="terminal-padding",
    )
    return WFSGlobalSolution(
        hypotheses=(hypothesis,),
        total_continuations=0,
        total_cost=0.0,
        total_ambiguous_steps=0,
        total_unresolved_steps=0,
        second_best_continuations=0 if margin is not None else None,
        second_best_cost=margin if margin is not None else None,
        alternative_cost_margin=margin,
        combinations_examined=2,
        search_truncated=truncated,
        notes=("synthetic global evidence",),
    )


def _fake_extract(output: Path, *, packets: int = 1, bytes_written: int = 20) -> ExtractResult:
    output.write_bytes(b"\x00\x00\x00\x01\x40\x01" + b"V" * max(0, bytes_written - 6))
    return ExtractResult(
        output=output,
        video_bytes=bytes_written,
        video_packets=packets,
        type_counts={0xFC: packets} if packets else {},
        codec_hint="hevc" if packets else None,
        codec_confidence=0.95 if packets else 0.0,
        trailing_unparsed_bytes=0,
        codec_reasons=("synthetic",),
    )


def test_global_recovery_surfaces_truncation_and_close_alternative(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"source")
    chain = WFSChain(0, 0, [0], None, False)
    solution = _solution(truncated=True, margin=0.5)
    monkeypatch.setattr(recovery, "build_global_chains", lambda *args, **kwargs: ([chain], solution))

    def extract(fd, fragments, output, **kwargs):
        return _fake_extract(output)

    monkeypatch.setattr(recovery, "extract_video", extract)
    candidates, manifest = recovery.recover_segment(
        source,
        [0],
        1,
        tmp_path / "out",
        label="global",
        strategy="global",
    )
    assert candidates[0].status == "REVIEW"
    assert candidates[0].reconstruction_strategy == "global"
    assert any("combination limit" in reason for reason in candidates[0].reasons)
    assert any("near-equivalent" in reason for reason in candidates[0].reasons)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["global_solution"]["search_truncated"] is True
    assert data["global_solution"]["alternative_cost_margin"] == 0.5
    assert data["global_solution"]["notes"] == ["synthetic global evidence"]


def test_recovery_zero_payload_is_fail_not_success(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"source")
    monkeypatch.setattr(
        recovery,
        "build_chains",
        lambda *args, **kwargs: [WFSChain(0, 0, [0], None, False)],
    )

    def extract(fd, fragments, output, **kwargs):
        output.write_bytes(b"")
        return ExtractResult(
            output=output,
            video_bytes=0,
            video_packets=0,
            type_counts={},
            codec_hint=None,
            codec_confidence=0.0,
            trailing_unparsed_bytes=0,
            codec_reasons=("no payload",),
        )

    monkeypatch.setattr(recovery, "extract_video", extract)
    candidates, _ = recovery.recover_segment(
        source,
        [0],
        1,
        tmp_path / "out",
        label="empty",
    )
    assert candidates[0].status == "FAIL"
    assert any("no native video" in reason for reason in candidates[0].reasons)


def test_recovery_marks_created_output_partial_after_extraction_error(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"source")
    monkeypatch.setattr(
        recovery,
        "build_chains",
        lambda *args, **kwargs: [WFSChain(0, 0, [0], None, False)],
    )

    def exploding_extract(fd, fragments, output, **kwargs):
        output.write_bytes(b"partial-evidence")
        raise RuntimeError("synthetic extraction failure")

    monkeypatch.setattr(recovery, "extract_video", exploding_extract)
    out = tmp_path / "out"
    with pytest.raises(RuntimeError, match="synthetic extraction failure"):
        recovery.recover_segment(source, [0], 1, out, label="partial")
    assert not (out / "partial_candidate_01.video.es").exists()
    assert (out / "partial_candidate_01.video.es.partial").read_bytes() == b"partial-evidence"


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"label": "bad/name"}, "label"),
        ({"label": "x", "strategy": "magic"}, "strategy"),
        ({"label": "x", "data_offset": -1}, "data_offset"),
    ],
)
def test_recovery_rejects_invalid_high_level_parameters(tmp_path: Path, kwargs, match) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"source")
    with pytest.raises(ValueError, match=match):
        recovery.recover_segment(source, [0], 1, tmp_path / "out", **kwargs)
