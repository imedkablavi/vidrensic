from __future__ import annotations

from pathlib import Path
import json
import stat

import pytest

from vidrensic.validation.private_run import PrivateValidationError, run_private_corpus


def _manifest(path: Path, source: Path, provenance: str = "lab") -> Path:
    digest = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "corpus_id": "private-test",
                "cases": [
                    {
                        "case_id": "case-1",
                        "source": source.name,
                        "family": "generic",
                        "provenance": provenance,
                        "redistributable": False,
                        "source_sha256": digest,
                        "expectations": [
                            {"kind": "source_hash", "expected": {"sha256": digest}}
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_private_runner_passes_non_synthetic_corpus_and_writes_0600_report(tmp_path: Path) -> None:
    source = tmp_path / "fixture.raw"
    source.write_bytes(b"fixture")
    manifest = _manifest(tmp_path / "corpus.json", source)
    report_path = tmp_path / "report.json"

    report = run_private_corpus(manifest, report_path)

    assert report.status == "PASS"
    assert report.passed == 1
    assert report.failed == 0
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "PASS"


def test_private_runner_rejects_synthetic_cases(tmp_path: Path) -> None:
    source = tmp_path / "fixture.raw"
    source.write_bytes(b"fixture")
    manifest = _manifest(tmp_path / "corpus.json", source, provenance="synthetic")

    with pytest.raises(PrivateValidationError, match="rejects synthetic"):
        run_private_corpus(manifest, tmp_path / "report.json")


def test_private_runner_rejects_manifest_inside_git_tree(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    source = repo / "fixture.raw"
    source.write_bytes(b"fixture")
    manifest = _manifest(repo / "corpus.json", source)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(PrivateValidationError, match="inside a Git working tree"):
        run_private_corpus(manifest, tmp_path / "report.json")


def test_private_runner_rejects_existing_report(tmp_path: Path) -> None:
    source = tmp_path / "fixture.raw"
    source.write_bytes(b"fixture")
    manifest = _manifest(tmp_path / "corpus.json", source)
    report = tmp_path / "report.json"
    report.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="output already exists"):
        run_private_corpus(manifest, report)
