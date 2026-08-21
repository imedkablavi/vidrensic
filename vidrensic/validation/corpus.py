from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
import json

from vidrensic import __version__
from vidrensic.core.hashing import hash_file
from vidrensic.plugins.defaults import default_plugin_registry
from vidrensic.plugins.wfs.recovery import recover_segment


class CorpusError(ValueError):
    pass


@dataclass(frozen=True)
class CorpusExpectation:
    kind: str
    parameters: dict[str, Any]
    expected: dict[str, Any]


@dataclass(frozen=True)
class CorpusCase:
    case_id: str
    source: Path
    family: str
    provenance: str
    redistributable: bool
    source_sha256: str | None
    expectations: tuple[CorpusExpectation, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationCorpus:
    corpus_id: str
    manifest_path: Path
    description: str
    cases: tuple[CorpusCase, ...]


@dataclass(frozen=True)
class ExpectationResult:
    kind: str
    status: str
    expected: dict[str, Any]
    actual: dict[str, Any]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CaseRunResult:
    case_id: str
    family: str
    source: str
    source_sha256: str
    status: str
    expectations: tuple[ExpectationResult, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CorpusRunReport:
    schema_version: int
    corpus_id: str
    manifest: str
    manifest_sha256: str
    vidrensic_version: str
    started_utc: str
    finished_utc: str
    status: str
    passed: int
    failed: int
    cases: tuple[CaseRunResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write_json(self, path: Path) -> None:
        path = path.expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(path)


def _contained_file(root: Path, relative: str) -> Path:
    if not relative or "\x00" in relative:
        raise CorpusError("case source path is empty or invalid")
    candidate = Path(relative)
    if candidate.is_absolute():
        raise CorpusError("corpus source paths must be relative to the manifest directory")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CorpusError(f"corpus source escapes manifest directory: {relative}") from exc
    if not resolved.exists() or not resolved.is_file():
        raise CorpusError(f"corpus source does not exist as a regular file: {relative}")
    if resolved.is_symlink():
        raise CorpusError(f"corpus source may not be a symlink: {relative}")
    return resolved


def _expectation_from_json(value: Any) -> CorpusExpectation:
    if not isinstance(value, dict):
        raise CorpusError("expectation entries must be objects")
    kind = value.get("kind")
    if not isinstance(kind, str) or not kind:
        raise CorpusError("expectation kind must be a non-empty string")
    parameters = value.get("parameters", {})
    expected = value.get("expected", {})
    if not isinstance(parameters, dict) or not isinstance(expected, dict):
        raise CorpusError("expectation parameters/expected must be objects")
    return CorpusExpectation(kind=kind, parameters=parameters, expected=expected)


def load_corpus(manifest: Path) -> ValidationCorpus:
    manifest = manifest.expanduser().resolve()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise CorpusError("validation corpus schema_version must be 1")
    corpus_id = data.get("corpus_id")
    if not isinstance(corpus_id, str) or not corpus_id:
        raise CorpusError("corpus_id must be a non-empty string")
    description = data.get("description", "")
    if not isinstance(description, str):
        raise CorpusError("description must be a string")
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise CorpusError("corpus must contain at least one case")

    root = manifest.parent.resolve()
    cases: list[CorpusCase] = []
    seen: set[str] = set()
    for row in raw_cases:
        if not isinstance(row, dict):
            raise CorpusError("case entries must be objects")
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise CorpusError("case_id must be a non-empty string")
        if case_id in seen:
            raise CorpusError(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        family = row.get("family")
        provenance = row.get("provenance")
        redistributable = row.get("redistributable")
        if not isinstance(family, str) or not family:
            raise CorpusError(f"case {case_id}: family must be a non-empty string")
        if provenance not in {"synthetic", "public", "lab", "restricted"}:
            raise CorpusError(f"case {case_id}: unsupported provenance classification")
        if not isinstance(redistributable, bool):
            raise CorpusError(f"case {case_id}: redistributable must be boolean")
        source_value = row.get("source")
        if not isinstance(source_value, str):
            raise CorpusError(f"case {case_id}: source must be a relative path")
        source = _contained_file(root, source_value)
        expected_hash = row.get("source_sha256")
        if expected_hash is not None:
            if not isinstance(expected_hash, str) or len(expected_hash) != 64:
                raise CorpusError(f"case {case_id}: source_sha256 must be 64 hex characters")
            try:
                bytes.fromhex(expected_hash)
            except ValueError as exc:
                raise CorpusError(f"case {case_id}: source_sha256 is not hexadecimal") from exc
            expected_hash = expected_hash.lower()
        raw_expectations = row.get("expectations", [])
        if not isinstance(raw_expectations, list) or not raw_expectations:
            raise CorpusError(f"case {case_id}: at least one expectation is required")
        expectations = tuple(_expectation_from_json(item) for item in raw_expectations)
        notes_value = row.get("notes", [])
        if not isinstance(notes_value, list) or not all(isinstance(item, str) for item in notes_value):
            raise CorpusError(f"case {case_id}: notes must be a list of strings")
        cases.append(
            CorpusCase(
                case_id=case_id,
                source=source,
                family=family,
                provenance=provenance,
                redistributable=redistributable,
                source_sha256=expected_hash,
                expectations=expectations,
                notes=tuple(notes_value),
            )
        )
    return ValidationCorpus(
        corpus_id=corpus_id,
        manifest_path=manifest,
        description=description,
        cases=tuple(cases),
    )


def _compare(expected: dict[str, Any], actual: dict[str, Any]) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    for key, value in expected.items():
        if key not in actual:
            reasons.append(f"missing actual field: {key}")
            continue
        if actual[key] != value:
            reasons.append(f"{key}: expected {value!r}, got {actual[key]!r}")
    return not reasons, tuple(reasons)


def _run_format_detect(source: Path, expectation: CorpusExpectation) -> dict[str, Any]:
    registry = default_plugin_registry()
    minimum_confidence = float(expectation.parameters.get("minimum_confidence", 0.60))
    minimum_margin = float(expectation.parameters.get("minimum_margin", 0.15))
    report = registry.detection_report(
        source,
        minimum_confidence=minimum_confidence,
        minimum_margin=minimum_margin,
    )
    best = report.best
    return {
        "top_plugin": None if best is None else best.plugin,
        "top_confidence": None if best is None else round(best.confidence, 6),
        "requires_review": report.requires_review,
        "result_count": len(report.results),
    }


def _run_wfs_recover(source: Path, expectation: CorpusExpectation) -> dict[str, Any]:
    params = expectation.parameters
    starts = params.get("starts")
    stop_fragment = params.get("stop_fragment")
    if not isinstance(starts, list) or not starts or not all(isinstance(item, int) for item in starts):
        raise CorpusError("wfs_recover parameters.starts must be a non-empty integer list")
    if not isinstance(stop_fragment, int):
        raise CorpusError("wfs_recover parameters.stop_fragment must be an integer")
    strategy = str(params.get("strategy", "global"))
    with TemporaryDirectory(prefix="vidrensic-validation-") as temp:
        candidates, manifest = recover_segment(
            source,
            starts,
            stop_fragment,
            Path(temp),
            label="validation",
            data_offset=int(params.get("data_offset", 0)),
            fragment_size=int(params.get("fragment_size", 2 * 1024 * 1024)),
            near=int(params.get("near", 32)),
            far=int(params.get("far", 4096)),
            strategy=strategy,
            candidate_top=int(params.get("candidate_top", 4)),
            beam_width=int(params.get("beam_width", 24)),
            max_hypotheses=int(params.get("max_hypotheses", 64)),
            max_combinations=int(params.get("max_combinations", 250_000)),
        )
        manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
        return {
            "strategy": strategy,
            "candidate_count": len(candidates),
            "candidate_fragments": [list(item.fragments) for item in candidates],
            "statuses": [item.status for item in candidates],
            "codecs": [item.codec_hint for item in candidates],
            "global_search_truncated": (
                None
                if manifest_data.get("global_solution") is None
                else bool(manifest_data["global_solution"].get("search_truncated"))
            ),
        }


def _run_expectation(source: Path, expectation: CorpusExpectation) -> dict[str, Any]:
    if expectation.kind == "source_hash":
        hashes = hash_file(source, ("sha256", "sha512"))
        return {"sha256": hashes["sha256"], "sha512": hashes["sha512"]}
    if expectation.kind == "format_detect":
        return _run_format_detect(source, expectation)
    if expectation.kind == "wfs_recover":
        return _run_wfs_recover(source, expectation)
    raise CorpusError(f"unsupported corpus expectation kind: {expectation.kind}")


def run_corpus(corpus: ValidationCorpus) -> CorpusRunReport:
    started = datetime.now(timezone.utc)
    manifest_sha256 = hash_file(corpus.manifest_path, ("sha256",))["sha256"]
    case_results: list[CaseRunResult] = []
    passed = 0
    failed = 0

    for case in corpus.cases:
        source_hash = hash_file(case.source, ("sha256",))["sha256"]
        case_reasons: list[str] = []
        results: list[ExpectationResult] = []
        if case.source_sha256 is not None and source_hash != case.source_sha256:
            case_reasons.append(
                f"source SHA-256 mismatch: expected {case.source_sha256}, got {source_hash}"
            )

        if not case_reasons:
            for expectation in case.expectations:
                try:
                    actual = _run_expectation(case.source, expectation)
                    ok, reasons = _compare(expectation.expected, actual)
                    status = "PASS" if ok else "FAIL"
                except Exception as exc:
                    actual = {}
                    reasons = (f"{type(exc).__name__}: {exc}",)
                    status = "ERROR"
                results.append(
                    ExpectationResult(
                        kind=expectation.kind,
                        status=status,
                        expected=expectation.expected,
                        actual=actual,
                        reasons=reasons,
                    )
                )

        if case_reasons or any(item.status != "PASS" for item in results):
            status = "FAIL"
            failed += 1
        else:
            status = "PASS"
            passed += 1
        case_results.append(
            CaseRunResult(
                case_id=case.case_id,
                family=case.family,
                source=str(case.source),
                source_sha256=source_hash,
                status=status,
                expectations=tuple(results),
                reasons=tuple(case_reasons),
            )
        )

    finished = datetime.now(timezone.utc)
    return CorpusRunReport(
        schema_version=1,
        corpus_id=corpus.corpus_id,
        manifest=str(corpus.manifest_path),
        manifest_sha256=manifest_sha256,
        vidrensic_version=__version__,
        started_utc=started.isoformat(),
        finished_utc=finished.isoformat(),
        status="PASS" if failed == 0 else "FAIL",
        passed=passed,
        failed=failed,
        cases=tuple(case_results),
    )
