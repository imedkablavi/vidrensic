from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json

import pytest

from vidrensic.crypto import KeyMaterial, decrypt_aes_file


AES128_KEY = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
PLAINTEXT = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")
CBC_IV = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
CBC_CIPHERTEXT = bytes.fromhex("7649abac8119b246cee98e9b12e9197d")
CTR_COUNTER = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff")
CTR_CIPHERTEXT = bytes.fromhex("874d6191b620e3261bef6864990db6ce")


def test_aes_cbc_known_answer_and_receipt_hides_key(tmp_path: Path) -> None:
    encrypted = tmp_path / "cbc.bin"
    encrypted.write_bytes(CBC_CIPHERTEXT)
    output = tmp_path / "cbc.clear"
    receipt_path = tmp_path / "cbc.receipt.json"
    key = KeyMaterial(AES128_KEY, source_label="NIST-known-answer")

    receipt = decrypt_aes_file(
        encrypted,
        output,
        key_material=key,
        iv=CBC_IV,
        mode="cbc",
        receipt_path=receipt_path,
    )
    assert output.read_bytes() == PLAINTEXT
    assert receipt.output_sha256 == sha256(PLAINTEXT).hexdigest()
    assert receipt.key_fingerprint_sha256 == sha256(AES128_KEY).hexdigest()

    text = receipt_path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert AES128_KEY.hex() not in text
    assert data["key_bits"] == 128
    assert data["mode"] == "cbc"
    assert data["output_sha256"] == sha256(PLAINTEXT).hexdigest()


def test_aes_ctr_known_answer(tmp_path: Path) -> None:
    encrypted = tmp_path / "ctr.bin"
    encrypted.write_bytes(CTR_CIPHERTEXT)
    output = tmp_path / "ctr.clear"
    receipt = decrypt_aes_file(
        encrypted,
        output,
        key_material=KeyMaterial(AES128_KEY),
        iv=CTR_COUNTER,
        mode="ctr",
    )
    assert output.read_bytes() == PLAINTEXT
    assert receipt.output_bytes == len(PLAINTEXT)
    assert receipt.mode == "ctr"


def test_crypto_refuses_overwrite_bad_lengths_and_bad_key(tmp_path: Path) -> None:
    encrypted = tmp_path / "bad.bin"
    encrypted.write_bytes(b"not-a-block")
    output = tmp_path / "out.bin"

    with pytest.raises(ValueError):
        KeyMaterial(b"short")
    with pytest.raises(ValueError):
        decrypt_aes_file(
            encrypted,
            output,
            key_material=KeyMaterial(AES128_KEY),
            iv=CBC_IV,
            mode="cbc",
        )

    encrypted.write_bytes(CBC_CIPHERTEXT)
    output.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        decrypt_aes_file(
            encrypted,
            output,
            key_material=KeyMaterial(AES128_KEY),
            iv=CBC_IV,
            mode="cbc",
        )


def test_pkcs7_cbc_unpadding(tmp_path: Path) -> None:
    # AES-CBC known one-block ciphertext decrypts to PLAINTEXT with no padding;
    # use the cryptography backend to construct a deterministic padded fixture.
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    padder = padding.PKCS7(128).padder()
    padded = padder.update(b"surveillance evidence") + padder.finalize()
    encryptor = Cipher(algorithms.AES(AES128_KEY), modes.CBC(CBC_IV)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    encrypted = tmp_path / "padded.bin"
    encrypted.write_bytes(ciphertext)
    output = tmp_path / "clear.bin"
    decrypt_aes_file(
        encrypted,
        output,
        key_material=KeyMaterial(AES128_KEY),
        iv=CBC_IV,
        mode="cbc",
        padding_mode="pkcs7",
    )
    assert output.read_bytes() == b"surveillance evidence"
