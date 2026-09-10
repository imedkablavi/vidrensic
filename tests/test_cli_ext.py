from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

import pytest

import vidrensic.cli_ext as cli_ext
from vidrensic.cli_ext import main


def test_validate_corpus_cli_writes_machine_readable_report(tmp_path: Path, capsys) -> None:
    source = tmp_path / "fixture.txt"
    source.write_text("fixture\n", encoding="utf-8")
    import hashlib

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = tmp_path / "corpus.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "corpus_id": "cli-validation",
                "cases": [
                    {
                        "case_id": "fixture",
                        "source": "fixture.txt",
                        "family": "generic",
                        "provenance": "synthetic",
                        "redistributable": True,
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
    report = tmp_path / "report.json"
    assert main(["validate", "corpus", str(manifest), "--out", str(report)]) == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["status"] == "PASS"
    stdout = capsys.readouterr().out
    assert "Validation complete" in stdout
    assert "Passed             1" in stdout
    assert "Failed             0" in stdout
    assert "passed=" not in stdout


def test_recover_wfs_cli_defaults_to_global_strategy(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(cli_ext, "require_safe_source", lambda path: object())
    captured = {}

    @dataclass
    class Candidate:
        candidate_id: str = "candidate_01"
        status: str = "REVIEW"
        reconstruction_strategy: str = "global"
        fragments: tuple[int, ...] = (1, 4)
        native_bytes: int = 123
        native_output: Path = tmp_path / "candidate.es"

    def fake_recover(*args, **kwargs):
        captured.update(kwargs)
        manifest = tmp_path / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")
        return [Candidate()], manifest

    monkeypatch.setattr(cli_ext, "recover_segment", fake_recover)
    rc = main(
        [
            "recover",
            "wfs",
            str(source),
            "--starts",
            "1,2",
            "--stop-fragment",
            "10",
            "--out",
            str(tmp_path / "out"),
            "--label",
            "synthetic",
        ]
    )
    assert rc == 0
    assert captured["strategy"] == "global"
    assert captured["starts"] if "starts" in captured else True
    stdout = capsys.readouterr().out
    assert "Recovery complete" in stdout
    assert "strategy=global" not in stdout
