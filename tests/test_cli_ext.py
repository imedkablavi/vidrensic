from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

import pytest

import vidrensic.cli_ext as cli_ext
from vidrensic.cli_ext import main


AES128_KEY_HEX = "2b7e151628aed2a6abf7158809cf4f3c"
PLAINTEXT = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")
CBC_IV_HEX = "000102030405060708090a0b0c0d0e0f"
CBC_CIPHERTEXT = bytes.fromhex("7649abac8119b246cee98e9b12e9197d")


def test_doctor_cli_json(monkeypatch, capsys) -> None:
    class Report:
        core_ready = True

        def to_dict(self):
            return {
                "product": "Vidrensic",
                "version": "test",
                "platform": "linux-test",
                "python": "3.x",
                "core_ready": True,
                "tools": [],
            }

    monkeypatch.setattr("vidrensic.cli_ext.run_doctor", lambda: Report())
    assert main(["doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["core_ready"] is True


def test_decrypt_aes_cli_never_prints_key(tmp_path: Path, capsys) -> None:
    encrypted = tmp_path / "input.bin"
    encrypted.write_bytes(CBC_CIPHERTEXT)
    key = tmp_path / "key.hex"
    key.write_text(AES128_KEY_HEX + "\n", encoding="ascii")
    output = tmp_path / "clear.bin"
    receipt = tmp_path / "receipt.json"

    assert (
        main(
            [
                "decrypt",
                "aes",
                str(encrypted),
                "--output",
                str(output),
                "--mode",
                "cbc",
                "--key-file",
                str(key),
                "--key-encoding",
                "hex",
                "--iv-hex",
                CBC_IV_HEX,
                "--receipt",
                str(receipt),
            ]
        )
        == 0
    )
    assert output.read_bytes() == PLAINTEXT
    stdout = capsys.readouterr().out
    assert AES128_KEY_HEX not in stdout
    assert AES128_KEY_HEX not in receipt.read_text(encoding="utf-8")


def test_decrypt_cli_rejects_invalid_iv(tmp_path: Path) -> None:
    encrypted = tmp_path / "input.bin"
    encrypted.write_bytes(CBC_CIPHERTEXT)
    key = tmp_path / "key.hex"
    key.write_text(AES128_KEY_HEX, encoding="ascii")
    with pytest.raises(SystemExit):
        main(
            [
                "decrypt",
                "aes",
                str(encrypted),
                "--output",
                str(tmp_path / "out.bin"),
                "--mode",
                "cbc",
                "--key-file",
                str(key),
                "--key-encoding",
                "hex",
                "--iv-hex",
                "00",
                "--receipt",
                str(tmp_path / "receipt.json"),
            ]
        )


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
    assert "passed=1" in stdout


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
    assert "strategy=global" in capsys.readouterr().out


def test_recover_wfs_cli_rejects_duplicate_starts(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "recover",
                "wfs",
                str(tmp_path / "source.raw"),
                "--starts",
                "1,1",
                "--stop-fragment",
                "10",
                "--out",
                str(tmp_path / "out"),
                "--label",
                "bad",
            ]
        )
