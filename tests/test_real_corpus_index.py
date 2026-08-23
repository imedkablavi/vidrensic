from __future__ import annotations

import pytest

from vidrensic.validation.real_corpus import RealCorpusIndexError, validate_real_corpus_index


def _case() -> dict:
    return {
        "case_id": "dhav-lab-001",
        "fixture_version": "1.0",
        "family": "dhav",
        "provenance": "lab",
        "source_sha256": "ab" * 32,
        "recorder": {
            "manufacturer": "Example Recorder Lab",
            "model": "controlled-fixture",
            "firmware": "known-build",
        },
        "acquisition": {
            "method": "write-blocked raw image",
            "date": "2026-08-24",
            "operator_role": "validation examiner",
        },
        "legal_basis": {
            "authority": "lab-owned validation recorder",
            "redistributable": False,
            "privacy_review": "contains only staged test footage",
        },
        "ground_truth": {
            "method": "recorder export plus synchronized reference clock",
            "reviewer_role": "independent lab reviewer",
            "expectations": [
                {"kind": "source_hash", "expected": {"sha256": "ab" * 32}},
            ],
        },
    }


def _index(cases: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "corpus_id": "real-v1",
        "corpus_version": "2026.08",
        "pass_semantics": "fixture-scoped only",
        "cases": cases,
    }


def test_zero_case_index_is_truthful_and_valid() -> None:
    validate_real_corpus_index(_index([]))


def test_valid_real_case_requires_complete_legal_and_ground_truth_metadata() -> None:
    validate_real_corpus_index(_index([_case()]))


def test_synthetic_case_cannot_be_admitted_as_real_validation() -> None:
    case = _case()
    case["provenance"] = "synthetic"
    with pytest.raises(RealCorpusIndexError, match="synthetic is not real validation"):
        validate_real_corpus_index(_index([case]))


def test_real_case_requires_source_hash() -> None:
    case = _case()
    del case["source_sha256"]
    with pytest.raises(RealCorpusIndexError, match="source_sha256"):
        validate_real_corpus_index(_index([case]))


def test_real_case_requires_legal_basis() -> None:
    case = _case()
    del case["legal_basis"]
    with pytest.raises(RealCorpusIndexError, match="legal_basis"):
        validate_real_corpus_index(_index([case]))


def test_real_case_requires_ground_truth_expectations() -> None:
    case = _case()
    case["ground_truth"]["expectations"] = []
    with pytest.raises(RealCorpusIndexError, match="expectations"):
        validate_real_corpus_index(_index([case]))
