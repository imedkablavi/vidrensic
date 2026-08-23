from __future__ import annotations

from pathlib import Path

from scripts.public_hygiene import path_policy_findings


def test_tracked_forensic_evidence_suffixes_fail_closed() -> None:
    for name in (
        "disk.E01",
        "disk.Ex01",
        "case.AFF4",
        "recorder.raw",
        "clip.DHAV",
        "video.mp4",
        "stream.h265",
    ):
        findings = path_policy_findings(Path("samples") / name)
        assert findings, name
        assert any("not explicitly allowlisted" in finding for finding in findings)


def test_case_and_evidence_roots_are_rejected_regardless_of_suffix() -> None:
    assert path_policy_findings(Path("cases/CASE-123/report.bin"))
    assert path_policy_findings(Path("evidence/device.bin"))
    assert path_policy_findings(Path("acquisitions/image.bin"))


def test_normal_repository_assets_are_not_treated_as_case_evidence() -> None:
    assert path_policy_findings(Path("docs/assets/vidrensic-mark.svg")) == []
    assert path_policy_findings(Path("validation_corpus/synthetic/hash-fixture.txt")) == []
