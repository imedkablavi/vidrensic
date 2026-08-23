from __future__ import annotations

from pathlib import Path
import os
import stat

import pytest

from vidrensic.crypto import KeyMaterial, decrypt_aes_file
from vidrensic.crypto.decrypt import MAX_KEY_FILE_BYTES


AES128_KEY = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
CBC_IV = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
CBC_CIPHERTEXT = bytes.fromhex("7649abac8119b246cee98e9b12e9197d")


def test_key_file_loader_is_bounded_for_raw_and_hex_inputs(tmp_path: Path) -> None:
    raw = tmp_path / "key.raw"
    raw.write_bytes(AES128_KEY)
    assert KeyMaterial.from_file(raw).key == AES128_KEY

    text = tmp_path / "key.hex"
    text.write_text(AES128_KEY.hex() + "\n", encoding="ascii")
    assert KeyMaterial.from_file(text, encoding="hex").key == AES128_KEY

    oversized = tmp_path / "huge.key"
    oversized.write_bytes(b"X" * (MAX_KEY_FILE_BYTES + 1))
    with pytest.raises(ValueError, match="refusing unbounded secret input"):
        KeyMaterial.from_file(oversized)


def test_decrypted_plaintext_and_receipt_are_owner_only_even_with_permissive_umask(
    tmp_path: Path,
) -> None:
    encrypted = tmp_path / "encrypted.bin"
    encrypted.write_bytes(CBC_CIPHERTEXT)
    output = tmp_path / "plaintext.bin"
    receipt = tmp_path / "receipt.json"

    previous_umask = os.umask(0)
    try:
        decrypt_aes_file(
            encrypted,
            output,
            key_material=KeyMaterial(AES128_KEY),
            iv=CBC_IV,
            mode="cbc",
            receipt_path=receipt,
        )
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert not output.with_name(output.name + ".partial").exists()
    assert not receipt.with_name(receipt.name + ".partial").exists()


def test_missing_key_file_fails_without_fabricating_material(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        KeyMaterial.from_file(tmp_path / "missing.key")
