from __future__ import annotations

from pathlib import Path
import json

import pytest

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
