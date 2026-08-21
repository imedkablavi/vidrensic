from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import struct

import pytest

from vidrensic.plugins.wfs.codec import FRAGMENT_SIZE
from vidrensic.validation.corpus import CorpusError, load_corpus, run_corpus


def _write_manifest(root: Path, data: dict) -> Path:
    path = root / "corpus.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _hevc_wfs_fragment() -> bytes:
    payload = (
        b"\x00\x00\x00\x01\x40\x01\x01"
        b"\x00\x00\x00\x01\x42\x01\x01"
        b"\x00\x00\x00\x01\x44\x01\x01"
        + b"validation" * 16
    )
    packet = b"\x00\x00\x01\xfc" + struct.pack("<I", len(payload)) + payload
    return packet + bytes(FRAGMENT_SIZE - len(packet))


def test_load_and_run_hash_ground_truth(tmp_path: Path) -> None:
    source = tmp_path / "fixture.bin"
    source.write_bytes(b"known-ground-truth")
    digest = sha256(source.read_bytes()).hexdigest()
    manifest = _write_manifest(
        tmp_path,
        {
            "schema_version": 1,
            "corpus_id": "synthetic-hash",
            "description": "minimal deterministic corpus",
            "cases": [
                {
                    "case_id": "hash-001",
                    "source": "fixture.bin",
                    "family": "generic",
                    "provenance": "synthetic",
                    "redistributable": True,
                    "source_sha256": digest,
                    "expectations": [
                        {"kind": "source_hash", "expected": {"sha256": digest}}
                    ],
                }
            ],
        },
    )
    report = run_corpus(load_corpus(manifest))
    assert report.status == "PASS"
    assert report.passed == 1
    assert report.failed == 0
    assert report.cases[0].expectations[0].status == "PASS"


def test_source_hash_mismatch_fails_before_operations(tmp_path: Path) -> None:
    (tmp_path / "fixture.bin").write_bytes(b"changed")
    manifest = _write_manifest(
        tmp_path,
        {
            "schema_version": 1,
            "corpus_id": "mismatch",
            "cases": [
                {
                    "case_id": "hash-001",
                    "source": "fixture.bin",
                    "family": "generic",
                    "provenance": "lab",
                    "redistributable": False,
                    "source_sha256": "00" * 32,
                    "expectations": [{"kind": "source_hash", "expected": {}}],
                }
            ],
        },
    )
    report = run_corpus(load_corpus(manifest))
    assert report.status == "FAIL"
    assert "mismatch" in report.cases[0].reasons[0]
    assert report.cases[0].expectations == ()


def test_corpus_rejects_path_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.bin"
    outside.write_bytes(b"outside")
    manifest = _write_manifest(
        tmp_path,
        {
            "schema_version": 1,
            "corpus_id": "escape",
            "cases": [
                {
                    "case_id": "escape-001",
                    "source": "../outside.bin",
                    "family": "generic",
                    "provenance": "restricted",
                    "redistributable": False,
                    "expectations": [{"kind": "source_hash", "expected": {}}],
                }
            ],
        },
    )
    with pytest.raises(CorpusError, match="escapes"):
        load_corpus(manifest)


def test_corpus_rejects_symlink_even_when_target_is_inside_root(tmp_path: Path) -> None:
    target = tmp_path / "real.bin"
    target.write_bytes(b"real")
    link = tmp_path / "link.bin"
    try:
        link.symlink_to(target.name)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")
    manifest = _write_manifest(
        tmp_path,
        {
            "schema_version": 1,
            "corpus_id": "symlink",
            "cases": [
                {
                    "case_id": "symlink-001",
                    "source": "link.bin",
                    "family": "generic",
                    "provenance": "lab",
                    "redistributable": False,
                    "expectations": [{"kind": "source_hash", "expected": {}}],
                }
            ],
        },
    )
    with pytest.raises(CorpusError, match="symlink"):
        load_corpus(manifest)


def test_corpus_executes_global_wfs_recovery_expectation(tmp_path: Path) -> None:
    source = tmp_path / "wfs.raw"
    source.write_bytes(_hevc_wfs_fragment())
    digest = sha256(source.read_bytes()).hexdigest()
    manifest = _write_manifest(
        tmp_path,
        {
            "schema_version": 1,
            "corpus_id": "synthetic-wfs",
            "cases": [
                {
                    "case_id": "wfs-single-terminal",
                    "source": "wfs.raw",
                    "family": "wfs",
                    "provenance": "synthetic",
                    "redistributable": True,
                    "source_sha256": digest,
                    "expectations": [
                        {
                            "kind": "wfs_recover",
                            "parameters": {
                                "starts": [0],
                                "stop_fragment": 1,
                                "strategy": "global",
                            },
                            "expected": {
                                "strategy": "global",
                                "candidate_count": 1,
                                "candidate_fragments": [[0]],
                                "statuses": ["UNKNOWN"],
                                "codecs": ["hevc"],
                                "global_search_truncated": False,
                            },
                        }
                    ],
                }
            ],
        },
    )
    report = run_corpus(load_corpus(manifest))
    assert report.status == "PASS"


def test_unsupported_expectation_is_reported_not_crashed(tmp_path: Path) -> None:
    source = tmp_path / "fixture.bin"
    source.write_bytes(b"fixture")
    manifest = _write_manifest(
        tmp_path,
        {
            "schema_version": 1,
            "corpus_id": "unsupported",
            "cases": [
                {
                    "case_id": "unsupported-001",
                    "source": "fixture.bin",
                    "family": "generic",
                    "provenance": "synthetic",
                    "redistributable": True,
                    "expectations": [{"kind": "not-real", "expected": {}}],
                }
            ],
        },
    )
    report = run_corpus(load_corpus(manifest))
    assert report.status == "FAIL"
    assert report.cases[0].expectations[0].status == "ERROR"
    assert "unsupported" in report.cases[0].expectations[0].reasons[0]


@pytest.mark.parametrize(
    "data,match",
    [
        ({"schema_version": 2, "corpus_id": "x", "cases": []}, "schema_version"),
        ({"schema_version": 1, "corpus_id": "", "cases": []}, "corpus_id"),
        ({"schema_version": 1, "corpus_id": "x", "cases": []}, "at least one case"),
    ],
)
def test_corpus_rejects_invalid_top_level_schema(tmp_path: Path, data: dict, match: str) -> None:
    manifest = _write_manifest(tmp_path, data)
    with pytest.raises(CorpusError, match=match):
        load_corpus(manifest)
