from __future__ import annotations

from collections import defaultdict
from typing import Any

from vidrensic.core.candidate_metadata import CandidateMetadata, MetadataClaim


_FIELDS = (
    "recording_start_utc",
    "recording_end_utc",
    "camera_slot",
    "source_label",
    "format_family",
)


def _field_projection(claims: list[MetadataClaim]) -> dict[str, Any]:
    values = sorted({claim.value for claim in claims})
    ambiguous = len(values) > 1
    evidence_claims = [claim for claim in claims if claim.evidence_backed]
    return {
        "value": None if ambiguous else values[0],
        "ambiguous": ambiguous,
        "claim_count": len(claims),
        "evidence_backed": bool(evidence_claims) and not ambiguous,
        "source_kinds": sorted({claim.source_kind for claim in claims}),
        "source_sha256s": sorted(
            {claim.source_sha256 for claim in evidence_claims if claim.source_sha256 is not None}
        ),
        "confidence": (
            max(claim.confidence for claim in evidence_claims)
            if evidence_claims
            else max(claim.confidence for claim in claims)
        ),
    }


def project_candidate_metadata(metadata: CandidateMetadata) -> dict[str, Any]:
    grouped: dict[str, list[MetadataClaim]] = defaultdict(list)
    for claim in metadata.claims:
        grouped[claim.field].append(claim)

    fields = {
        field: _field_projection(grouped[field])
        for field in sorted(grouped)
        if field in _FIELDS
    }
    values = {
        field: details["value"]
        for field, details in fields.items()
        if details["value"] is not None
    }
    return {
        "item_id": metadata.item_id,
        "artifact_sha256": metadata.artifact_sha256,
        **{field: values.get(field) for field in _FIELDS},
        "fields": fields,
        "claims": [claim.to_dict() for claim in metadata.claims],
        "evidence_backed": any(
            bool(details["evidence_backed"]) for details in fields.values()
        ),
    }
