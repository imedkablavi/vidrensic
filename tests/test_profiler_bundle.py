from __future__ import annotations

from pathlib import Path
import json
import stat

from vidrensic.profiler.bundle import build_anonymized_bundle
from vidrensic.profiler.triage import TriageReport


def _report(source: Path) -> TriageReport:
    return TriageReport(
        source=source,
        source_info={
            "path": str(source),
            "size_bytes": 8 * 1024**3,
            "is_block_device": True,
            "read_only": True,
            "mounted_at": ("/media/private",),
        },
        storage={
            "partition_scheme": "GPT",
            "sector_size": 4096,
            "partitions": [
                {"unique_id": "secret-guid", "name": "CASE-123", "size_bytes": 1234}
            ],
            "filesystems": [
                {"family": "NTFS", "confidence": 0.99, "offset": 123456}
            ],
        },
        sample_profile={
            "samples": [
                {
                    "offset": 123,
                    "sha256": "secret-hash",
                    "entropy_bits_per_byte": 7.1,
                    "zero_fraction": 0.1,
                    "ff_fraction": 0.2,
                    "annexb_start_codes": 3,
                }
            ],
            "sample_size": 4 * 1024 * 1024,
            "aggregate_signatures": {"DHAV": 12},
        },
        format_detection={
            "requires_review": True,
            "results": [
                {
                    "plugin": "wfs",
                    "confidence": 0.72,
                    "metadata": {"serial": "secret"},
                }
            ],
        },
        hitmap={
            "scanned_bytes": 512 * 1024 * 1024,
            "chunk_size": 16 * 1024 * 1024,
            "signatures": [
                {
                    "signature_id": "wfs_0_5_ascii",
                    "category": "storage-family",
                    "evidence_strength": "supporting",
                    "count": 7,
                    "first_offset": 9999,
                    "last_offset": 10009,
                    "retained_offsets": [9999],
                    "pattern_hex": "secret-pattern",
                    "hits_per_gib_scanned": 14.0,
                }
            ],
        },
    )


def test_bundle_strips_identifiers_and_offsets(tmp_path: Path) -> None:
    source = tmp_path / "CASE-123_RECORDER.img"
    report = _report(source)
    bundle = build_anonymized_bundle(report)
    payload = bundle.to_dict()
    encoded = json.dumps(payload, sort_keys=True)

    assert payload["bundle_type"] == "anonymized-profiler-bundle"
    assert str(source) not in encoded
    assert "secret-guid" not in encoded
    assert "CASE-123" not in encoded
    assert "secret-hash" not in encoded
    assert "secret-pattern" not in encoded
    assert "9999" not in encoded
    assert payload["source"]["size_bucket"] == "4–16 GiB"
    assert payload["storage"]["filesystem_families"][0]["family"] == "NTFS"
    assert payload["storage"]["filesystem_families"][0]["confidence"] == "high"
    assert payload["format_detection"]["results"][0]["confidence"] == "moderate"


def test_bundle_write_is_owner_only(tmp_path: Path) -> None:
    source = tmp_path / "source.img"
    output = tmp_path / "bundle.json"
    bundle = build_anonymized_bundle(_report(source))

    bundle.write_json(output)

    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == 1
