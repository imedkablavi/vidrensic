from __future__ import annotations

from typing import Any


class RealCorpusIndexError(ValueError):
    pass


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RealCorpusIndexError(f"{field} must be a non-empty string")
    return value.strip()


def _sha256(value: Any, field: str) -> str:
    text = _nonempty_string(value, field).lower()
    if len(text) != 64:
        raise RealCorpusIndexError(f"{field} must contain 64 hexadecimal characters")
    try:
        bytes.fromhex(text)
    except ValueError as exc:
        raise RealCorpusIndexError(f"{field} must be hexadecimal") from exc
    return text


def validate_real_corpus_index(data: Any) -> None:
    """Validate admission metadata for the versioned real-recorder corpus.

    This validates provenance/ground-truth metadata only. It deliberately allows
    a zero-case index, which means no real-recorder compatibility is established.
    """

    if not isinstance(data, dict):
        raise RealCorpusIndexError("index must be a JSON object")
    if data.get("schema_version") != 1:
        raise RealCorpusIndexError("schema_version must be 1")
    _nonempty_string(data.get("corpus_id"), "corpus_id")
    _nonempty_string(data.get("corpus_version"), "corpus_version")
    _nonempty_string(data.get("pass_semantics"), "pass_semantics")
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise RealCorpusIndexError("cases must be a list")

    seen: set[str] = set()
    for number, case in enumerate(cases):
        prefix = f"cases[{number}]"
        if not isinstance(case, dict):
            raise RealCorpusIndexError(f"{prefix} must be an object")
        case_id = _nonempty_string(case.get("case_id"), f"{prefix}.case_id")
        if case_id in seen:
            raise RealCorpusIndexError(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        _nonempty_string(case.get("fixture_version"), f"{prefix}.fixture_version")
        family = _nonempty_string(case.get("family"), f"{prefix}.family")
        if family not in {"wfs", "dhav", "hikvision", "annexb", "mpegps", "generic"}:
            raise RealCorpusIndexError(f"{prefix}.family is unsupported: {family}")
        provenance = case.get("provenance")
        if provenance not in {"public", "lab", "restricted"}:
            raise RealCorpusIndexError(
                f"{prefix}.provenance must be public, lab or restricted; synthetic is not real validation"
            )
        _sha256(case.get("source_sha256"), f"{prefix}.source_sha256")

        recorder = case.get("recorder")
        if not isinstance(recorder, dict):
            raise RealCorpusIndexError(f"{prefix}.recorder must be an object")
        for field in ("manufacturer", "model", "firmware"):
            _nonempty_string(recorder.get(field), f"{prefix}.recorder.{field}")

        acquisition = case.get("acquisition")
        if not isinstance(acquisition, dict):
            raise RealCorpusIndexError(f"{prefix}.acquisition must be an object")
        for field in ("method", "date", "operator_role"):
            _nonempty_string(acquisition.get(field), f"{prefix}.acquisition.{field}")

        legal = case.get("legal_basis")
        if not isinstance(legal, dict):
            raise RealCorpusIndexError(f"{prefix}.legal_basis must be an object")
        _nonempty_string(legal.get("authority"), f"{prefix}.legal_basis.authority")
        if not isinstance(legal.get("redistributable"), bool):
            raise RealCorpusIndexError(f"{prefix}.legal_basis.redistributable must be boolean")
        _nonempty_string(legal.get("privacy_review"), f"{prefix}.legal_basis.privacy_review")

        truth = case.get("ground_truth")
        if not isinstance(truth, dict):
            raise RealCorpusIndexError(f"{prefix}.ground_truth must be an object")
        _nonempty_string(truth.get("method"), f"{prefix}.ground_truth.method")
        _nonempty_string(truth.get("reviewer_role"), f"{prefix}.ground_truth.reviewer_role")
        expectations = truth.get("expectations")
        if not isinstance(expectations, list) or not expectations:
            raise RealCorpusIndexError(
                f"{prefix}.ground_truth.expectations must be a non-empty list"
            )
        for expectation_index, expectation in enumerate(expectations):
            if not isinstance(expectation, dict):
                raise RealCorpusIndexError(
                    f"{prefix}.ground_truth.expectations[{expectation_index}] must be an object"
                )
            _nonempty_string(
                expectation.get("kind"),
                f"{prefix}.ground_truth.expectations[{expectation_index}].kind",
            )
            if "expected" not in expectation:
                raise RealCorpusIndexError(
                    f"{prefix}.ground_truth.expectations[{expectation_index}].expected is required"
                )
