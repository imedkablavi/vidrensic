from __future__ import annotations

from pathlib import Path
import json

import pytest

import vidrensic.validation.corpus as corpus_module
import vidrensic.validation.real_corpus as real_module
from vidrensic.validation.corpus import CorpusError, CorpusExpectation, load_corpus
from vidrensic.validation.real_corpus import RealCorpusIndexError, validate_real_corpus_index


def _write_json(path: Path, data) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _minimal_case(source: str = "fixture.bin") -> dict:
    return {
        "case_id": "case-1",
        "source": source,
        "family": "generic",
        "provenance": "synthetic",
        "redistributable": True,
        "expectations": [{"kind": "source_hash", "expected": {}}],
    }


def test_validation_manifest_size_is_checked_before_schema_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(corpus_module, "MAX_CORPUS_MANIFEST_BYTES", 64)
    manifest = tmp_path / "corpus.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "corpus_id": "x",
                "description": "A" * 128,
                "cases": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CorpusError, match="maximum size"):
        load_corpus(manifest)


def test_validation_manifest_case_and_expectation_fanout_are_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(corpus_module, "MAX_CORPUS_CASES", 1)
    manifest = _write_json(
        tmp_path / "too-many-cases.json",
        {
            "schema_version": 1,
            "corpus_id": "fanout",
            "cases": [{}, {}],
        },
    )
    with pytest.raises(CorpusError, match="exceeds 1 cases"):
        load_corpus(manifest)

    source = tmp_path / "fixture.bin"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(corpus_module, "MAX_CORPUS_CASES", 4096)
    monkeypatch.setattr(corpus_module, "MAX_EXPECTATIONS_PER_CASE", 1)
    case = _minimal_case()
    case["expectations"] = [
        {"kind": "source_hash", "expected": {}},
        {"kind": "source_hash", "expected": {}},
    ]
    manifest = _write_json(
        tmp_path / "too-many-expectations.json",
        {"schema_version": 1, "corpus_id": "fanout", "cases": [case]},
    )
    with pytest.raises(CorpusError, match="expectations exceed 1 entries"):
        load_corpus(manifest)


def test_validation_manifest_notes_and_wfs_start_lists_are_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "fixture.bin"
    source.write_bytes(b"fixture")

    monkeypatch.setattr(corpus_module, "MAX_NOTES_PER_CASE", 1)
    case = _minimal_case()
    case["notes"] = ["one", "two"]
    manifest = _write_json(
        tmp_path / "too-many-notes.json",
        {"schema_version": 1, "corpus_id": "notes", "cases": [case]},
    )
    with pytest.raises(CorpusError, match="notes exceed 1 entries"):
        load_corpus(manifest)

    monkeypatch.setattr(corpus_module, "MAX_WFS_STARTS_PER_EXPECTATION", 1)
    expectation = CorpusExpectation(
        kind="wfs_recover",
        parameters={"starts": [0, 1], "stop_fragment": 2},
        expected={},
    )
    with pytest.raises(CorpusError, match="starts exceeds 1 entries"):
        corpus_module._run_wfs_recover(source, expectation)


def _real_index(cases: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "corpus_id": "real-v1",
        "corpus_version": "2026.08",
        "pass_semantics": "fixture scoped",
        "cases": cases,
    }


def _real_case() -> dict:
    return {
        "case_id": "real-1",
        "fixture_version": "1",
        "family": "dhav",
        "provenance": "lab",
        "source_sha256": "ab" * 32,
        "recorder": {"manufacturer": "lab", "model": "fixture", "firmware": "1"},
        "acquisition": {
            "method": "write-blocked image",
            "date": "2026-08-24",
            "operator_role": "examiner",
        },
        "legal_basis": {
            "authority": "lab owned",
            "redistributable": False,
            "privacy_review": "staged footage",
        },
        "ground_truth": {
            "method": "reference export",
            "reviewer_role": "reviewer",
            "expectations": [{"kind": "source_hash", "expected": {"sha256": "ab" * 32}}],
        },
    }


def test_real_index_case_expectation_and_text_fanout_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(real_module, "MAX_REAL_CORPUS_CASES", 1)
    with pytest.raises(RealCorpusIndexError, match="cases exceeds 1 entries"):
        validate_real_corpus_index(_real_index([{}, {}]))

    monkeypatch.setattr(real_module, "MAX_REAL_CORPUS_CASES", 4096)
    monkeypatch.setattr(real_module, "MAX_REAL_EXPECTATIONS_PER_CASE", 1)
    case = _real_case()
    case["ground_truth"]["expectations"] *= 2
    with pytest.raises(RealCorpusIndexError, match="expectations exceeds 1 entries"):
        validate_real_corpus_index(_real_index([case]))

    monkeypatch.setattr(real_module, "MAX_REAL_EXPECTATIONS_PER_CASE", 1024)
    monkeypatch.setattr(real_module, "MAX_REAL_TEXT_CHARS", 8)
    with pytest.raises(RealCorpusIndexError, match="corpus_version exceeds 8 characters"):
        validate_real_corpus_index(_real_index([]))
