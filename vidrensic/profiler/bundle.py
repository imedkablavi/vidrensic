from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import math

from vidrensic import __product__, __version__
from vidrensic.core.private_io import atomic_write_private_json
from vidrensic.profiler.triage import TriageReport


SIZE_BUCKETS = (
    (0, 64 * 1024 * 1024, "<64 MiB"),
    (64 * 1024 * 1024, 1024**3, "64 MiB–1 GiB"),
    (1024**3, 4 * 1024**3, "1–4 GiB"),
    (4 * 1024**3, 16 * 1024**3, "4–16 GiB"),
    (16 * 1024**3, 64 * 1024**3, "16–64 GiB"),
    (64 * 1024**3, 256 * 1024**3, "64–256 GiB"),
    (256 * 1024**3, 1024**4, "256 GiB–1 TiB"),
    (1024**4, math.inf, ">1 TiB"),
)


@dataclass(frozen=True)
class AnonymizedProfilerBundle:
    schema_version: int
    bundle_type: str
    product: str
    version: str
    source: dict[str, Any]
    storage: dict[str, Any]
    samples: dict[str, Any]
    format_detection: dict[str, Any]
    signature_map: dict[str, Any]
    workflow: dict[str, Any]
    claim_boundary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "bundle_type": self.bundle_type,
            "product": self.product,
            "version": self.version,
            "source": self.source,
            "storage": self.storage,
            "samples": self.samples,
            "format_detection": self.format_detection,
            "signature_map": self.signature_map,
            "workflow": self.workflow,
            "claim_boundary": self.claim_boundary,
        }

    def write_json(self, output: Path, *, replace: bool = False) -> Path:
        return atomic_write_private_json(output, self.to_dict(), allow_replace=replace)


def size_bucket(value: int | None) -> str:
    if value is None or value < 0:
        return "unknown"
    for lower, upper, label in SIZE_BUCKETS:
        if lower <= value < upper:
            return label
    return "unknown"


def _band(value: float | None, thresholds: tuple[float, float], labels: tuple[str, str, str]) -> str:
    if value is None:
        return "unknown"
    low, high = thresholds
    if value < low:
        return labels[0]
    if value < high:
        return labels[1]
    return labels[2]


def confidence_band(value: float | None) -> str:
    return _band(value, (0.65, 0.85), ("low", "moderate", "high"))


def _range_band(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"min": None, "max": None}
    return {
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _sanitize_storage(storage: dict[str, Any]) -> dict[str, Any]:
    filesystems = storage.get("filesystems", [])
    family_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in filesystems if isinstance(filesystems, list) else []:
        if not isinstance(row, dict):
            continue
        family = str(row.get("family", "unknown"))
        if family in seen:
            continue
        seen.add(family)
        family_rows.append(
            {
                "family": family,
                "confidence": confidence_band(_as_float(row.get("confidence"))),
            }
        )
    return {
        "partition_scheme": storage.get("partition_scheme"),
        "sector_size": storage.get("sector_size"),
        "partition_count": len(storage.get("partitions", [])) if isinstance(storage.get("partitions", []), list) else 0,
        "filesystem_families": sorted(family_rows, key=lambda item: item["family"]),
    }


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sanitize_samples(samples: dict[str, Any]) -> dict[str, Any]:
    rows = samples.get("samples", [])
    entropies: list[float] = []
    zeros: list[float] = []
    ffs: list[float] = []
    annexb_hits = 0
    for sample in rows if isinstance(rows, list) else []:
        if not isinstance(sample, dict):
            continue
        for key, target in (
            ("entropy_bits_per_byte", entropies),
            ("zero_fraction", zeros),
            ("ff_fraction", ffs),
        ):
            number = _as_float(sample.get(key))
            if number is not None:
                target.append(number)
        annexb_hits += int(sample.get("annexb_start_codes", 0) or 0) > 0

    aggregate = samples.get("aggregate_signatures", {})
    safe_signatures: dict[str, int] = {}
    if isinstance(aggregate, dict):
        for key, value in aggregate.items():
            number = _as_float(value)
            if number is not None and number >= 0:
                safe_signatures[str(key)] = int(number)

    return {
        "sample_count": len(rows) if isinstance(rows, list) else 0,
        "sample_size_bucket": size_bucket(samples.get("sample_size")),
        "entropy_bits_per_byte": _range_band(entropies),
        "zero_fraction": _range_band(zeros),
        "ff_fraction": _range_band(ffs),
        "samples_with_annexb_evidence": annexb_hits,
        "aggregate_signatures": safe_signatures,
    }


def _sanitize_detection(detection: dict[str, Any]) -> dict[str, Any]:
    results = detection.get("results", [])
    safe_results: list[dict[str, Any]] = []
    for row in results if isinstance(results, list) else []:
        if not isinstance(row, dict):
            continue
        safe_results.append(
            {
                "plugin": str(row.get("plugin", "unknown")),
                "confidence": confidence_band(_as_float(row.get("confidence"))),
            }
        )
    return {
        "requires_review": bool(detection.get("requires_review", True)),
        "results": safe_results[:8],
    }


def _sanitize_hitmap(hitmap: dict[str, Any]) -> dict[str, Any]:
    signatures = hitmap.get("signatures", [])
    safe_signatures: list[dict[str, Any]] = []
    for row in signatures if isinstance(signatures, list) else []:
        if not isinstance(row, dict):
            continue
        safe_signatures.append(
            {
                "signature_id": str(row.get("signature_id", "unknown")),
                "category": str(row.get("category", "unknown")),
                "evidence_strength": str(row.get("evidence_strength", "lead")),
                "count": int(row.get("count", 0) or 0),
                "hits_per_gib_scanned": round(float(row.get("hits_per_gib_scanned", 0.0) or 0.0), 4),
            }
        )
    return {
        "scanned_size_bucket": size_bucket(hitmap.get("scanned_bytes")),
        "chunk_size_bucket": size_bucket(hitmap.get("chunk_size")),
        "signatures": safe_signatures,
    }


def _workflow_flags(report: TriageReport) -> dict[str, Any]:
    detection = report.format_detection
    top = detection.get("results", [])
    top_plugin = str(top[0].get("plugin")) if top and isinstance(top[0], dict) else None
    return {
        "review_required": bool(detection.get("requires_review", True)),
        "top_family": top_plugin,
        "recommended_stage": _stage_for_family(top_plugin, bool(detection.get("requires_review", True))),
    }


def _stage_for_family(plugin: str | None, requires_review: bool) -> str:
    if requires_review or plugin is None:
        return "profile_and_review"
    return {
        "wfs": "wfs_layout_profile",
        "dhav": "dhav_structure_review",
        "hikvision": "recorder_profile_review",
        "annexb": "payload_layer_review",
        "mpegps": "payload_layer_review",
    }.get(plugin, "profile_and_review")


def build_anonymized_bundle(report: TriageReport) -> AnonymizedProfilerBundle:
    source_info = report.source_info
    size_bytes = _as_float(source_info.get("size_bytes"))
    source = {
        "kind": "block-device" if source_info.get("is_block_device") else "file",
        "size_bucket": size_bucket(int(size_bytes)) if size_bytes is not None else "unknown",
        "read_only": source_info.get("read_only"),
        "mounted": bool(source_info.get("mounted_at")),
    }
    return AnonymizedProfilerBundle(
        schema_version=1,
        bundle_type="anonymized-profiler-bundle",
        product=__product__,
        version=__version__,
        source=source,
        storage=_sanitize_storage(report.storage),
        samples=_sanitize_samples(report.sample_profile),
        format_detection=_sanitize_detection(report.format_detection),
        signature_map=_sanitize_hitmap(report.hitmap),
        workflow=_workflow_flags(report),
        claim_boundary=(
            "This bundle contains anonymized profiler metadata only. It does not contain evidence bytes, "
            "source paths, source hashes, device serials, GUIDs, exact offsets or recorder support proof."
        ),
    )
