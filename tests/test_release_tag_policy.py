from __future__ import annotations

from pathlib import Path
import json

import pytest

from scripts.check_release_tag_policy import (
    ReleaseTagPolicyError,
    evaluate_release_tag_policy,
)


def _index(path: Path, *, cases: list[dict] | None = None) -> Path:
    payload = {
        "schema_version": 1,
        "corpus_id": "vidrensic-real-recorder-v1",
        "corpus_version": "2026.08",
        "status": "awaiting-authorized-fixtures" if not cases else "fixtures-present",
        "pass_semantics": (
            "PASS applies only to the exact hashed fixture, manifest version and commit."
        ),
        "cases": cases or [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _real_case() -> dict:
    return {
        "case_id": "lab-wfs-001",
        "fixture_version": "1",
        "family": "wfs",
        "provenance": "lab",
        "source_sha256": "ab" * 32,
        "recorder": {
            "manufacturer": "Example",
            "model": "Recorder-1",
            "firmware": "1.0",
        },
        "acquisition": {
            "method": "forensic image",
            "date": "2026-08-24",
            "operator_role": "lab examiner",
        },
        "legal_basis": {
            "authority": "authorized lab fixture",
            "redistributable": False,
            "privacy_review": "approved for restricted validation",
        },
        "ground_truth": {
            "method": "independent recorder playback comparison",
            "reviewer_role": "second examiner",
            "expectations": [{"kind": "recording_count", "expected": 1}],
        },
    }


def test_workflow_dispatch_is_qualification_only_even_with_empty_real_corpus(tmp_path: Path) -> None:
    result = evaluate_release_tag_policy(
        ref_name="main",
        ref_type="branch",
        package_version="0.6.0a0",
        real_index_path=_index(tmp_path / "index.json"),
    )

    assert result["mode"] == "qualification-only"
    assert result["release_channel"] is None
    assert result["real_case_count"] is None


@pytest.mark.parametrize("version", ["0.6.0a0", "0.6.0b1", "0.6.0rc1", "0.6.0.dev1"])
def test_prerelease_tag_allows_empty_real_corpus(tmp_path: Path, version: str) -> None:
    result = evaluate_release_tag_policy(
        ref_name=f"v{version}",
        ref_type="tag",
        package_version=version,
        real_index_path=_index(tmp_path / "index.json"),
    )

    assert result["release_channel"] == "prerelease"
    assert result["real_case_count"] == 0


def test_stable_tag_is_blocked_when_real_corpus_is_empty(tmp_path: Path) -> None:
    with pytest.raises(ReleaseTagPolicyError, match="zero cases"):
        evaluate_release_tag_policy(
            ref_name="v1.0.0",
            ref_type="tag",
            package_version="1.0.0",
            real_index_path=_index(tmp_path / "index.json"),
        )


def test_stable_tag_passes_minimum_automated_gate_with_admitted_case(tmp_path: Path) -> None:
    result = evaluate_release_tag_policy(
        ref_name="v1.0.0",
        ref_type="tag",
        package_version="1.0.0",
        real_index_path=_index(tmp_path / "index.json", cases=[_real_case()]),
    )

    assert result["release_channel"] == "stable"
    assert result["real_case_count"] == 1


def test_tag_must_match_package_version_exactly(tmp_path: Path) -> None:
    with pytest.raises(ReleaseTagPolicyError, match="does not match package version"):
        evaluate_release_tag_policy(
            ref_name="v1.0.0",
            ref_type="tag",
            package_version="1.0.1",
            real_index_path=_index(tmp_path / "index.json", cases=[_real_case()]),
        )


def test_tag_requires_v_prefix(tmp_path: Path) -> None:
    with pytest.raises(ReleaseTagPolicyError, match="v<version>"):
        evaluate_release_tag_policy(
            ref_name="1.0.0",
            ref_type="tag",
            package_version="1.0.0",
            real_index_path=_index(tmp_path / "index.json", cases=[_real_case()]),
        )
