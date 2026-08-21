from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256, sha512
from pathlib import Path
from typing import Literal
import json
import os

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


AESMode = Literal["cbc", "ctr"]
PaddingMode = Literal["none", "pkcs7"]


@dataclass(frozen=True)
class KeyMaterial:
    """Secret key bytes plus non-secret provenance metadata.

    `key` is deliberately excluded from repr/serialization. Receipts record only
    a SHA-256 fingerprint, length and source label. Python cannot guarantee that
    immutable secret bytes are physically zeroized from process memory.
    """

    key: bytes = field(repr=False)
    source_label: str = "provided-key"

    def __post_init__(self) -> None:
        if len(self.key) not in (16, 24, 32):
            raise ValueError("AES key must be 16, 24 or 32 bytes")
        if not self.source_label.strip():
            raise ValueError("key source_label cannot be empty")

    @classmethod
    def from_file(cls, path: Path, *, encoding: Literal["raw", "hex"] = "raw") -> KeyMaterial:
        path = path.expanduser().resolve()
        data = path.read_bytes()
        if encoding == "hex":
            try:
                data = bytes.fromhex(data.decode("ascii").strip())
            except (UnicodeDecodeError, ValueError) as exc:
                raise ValueError("key file is not valid hexadecimal text") from exc
        elif encoding != "raw":
            raise ValueError("key encoding must be raw or hex")
        return cls(data, source_label=f"file:{path.name}")

    @property
    def fingerprint_sha256(self) -> str:
        return sha256(self.key).hexdigest()


@dataclass(frozen=True)
class DecryptionReceipt:
    algorithm: str
    mode: AESMode
    padding: PaddingMode
    input_path: Path
    output_path: Path
    input_bytes: int
    output_bytes: int
    input_sha256: str
    input_sha512: str
    output_sha256: str
    output_sha512: str
    key_fingerprint_sha256: str
    key_bits: int
    key_source_label: str
    iv_hex: str

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "operation": "decrypt",
            "algorithm": self.algorithm,
            "mode": self.mode,
            "padding": self.padding,
            "input_path": str(self.input_path),
            "output_path": str(self.output_path),
            "input_bytes": self.input_bytes,
            "output_bytes": self.output_bytes,
            "input_sha256": self.input_sha256,
            "input_sha512": self.input_sha512,
            "output_sha256": self.output_sha256,
            "output_sha512": self.output_sha512,
            "key_fingerprint_sha256": self.key_fingerprint_sha256,
            "key_bits": self.key_bits,
            "key_source_label": self.key_source_label,
            "iv_hex": self.iv_hex,
            "forensic_notes": [
                "secret key bytes are intentionally excluded from the receipt",
                "successful cryptographic transformation does not prove the recorder/container interpretation",
                "input and output hashes bind this receipt to exact byte streams",
            ],
        }

    def write_json(self, path: Path) -> Path:
        path = path.expanduser().resolve()
        if path.exists():
            raise FileExistsError(f"receipt already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".partial")
        if temp.exists():
            raise FileExistsError(f"partial receipt already exists: {temp}")
        try:
            with temp.open("x", encoding="utf-8") as fh:
                json.dump(self.to_dict(), fh, indent=2, sort_keys=True)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            temp.replace(path)
        except Exception:
            if temp.exists():
                temp.unlink()
            raise
        return path


def _cipher(key: bytes, mode: AESMode, iv: bytes) -> Cipher:
    if len(iv) != 16:
        raise ValueError("AES CBC/CTR IV/counter must be exactly 16 bytes")
    algorithm = algorithms.AES(key)
    if mode == "cbc":
        return Cipher(algorithm, modes.CBC(iv))
    if mode == "ctr":
        return Cipher(algorithm, modes.CTR(iv))
    raise ValueError("mode must be cbc or ctr")


def decrypt_aes_file(
    input_path: Path,
    output_path: Path,
    *,
    key_material: KeyMaterial,
    iv: bytes,
    mode: AESMode,
    padding_mode: PaddingMode = "none",
    chunk_size: int = 4 * 1024 * 1024,
    receipt_path: Path | None = None,
) -> DecryptionReceipt:
    """Decrypt a file with explicitly supplied AES parameters.

    This primitive deliberately does not discover keys, IVs or vendor-specific
    encryption layouts. Format plugins must establish those parameters from
    recorder metadata/evidence before calling it.
    """

    input_path = input_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if output_path == input_path:
        raise ValueError("output cannot overwrite the encrypted input")
    if output_path.exists():
        raise FileExistsError(f"decryption output already exists: {output_path}")
    if chunk_size < 4096 or chunk_size > 64 * 1024 * 1024:
        raise ValueError("chunk_size must be between 4 KiB and 64 MiB")
    if padding_mode not in ("none", "pkcs7"):
        raise ValueError("padding_mode must be none or pkcs7")
    if mode == "ctr" and padding_mode != "none":
        raise ValueError("CTR mode does not use PKCS#7 padding")

    input_size = input_path.stat().st_size
    if mode == "cbc" and input_size % 16:
        raise ValueError("AES-CBC ciphertext length must be a multiple of 16 bytes")

    cipher = _cipher(key_material.key, mode, iv)
    decryptor = cipher.decryptor()
    unpadder = padding.PKCS7(128).unpadder() if padding_mode == "pkcs7" else None

    in256, in512 = sha256(), sha512()
    out256, out512 = sha256(), sha512()
    output_bytes = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_name(output_path.name + ".partial")
    if partial.exists():
        raise FileExistsError(f"partial decryption output already exists: {partial}")

    try:
        with input_path.open("rb", buffering=0) as source, partial.open("xb", buffering=0) as target:
            while True:
                chunk = source.read(chunk_size)
                if not chunk:
                    break
                in256.update(chunk)
                in512.update(chunk)
                clear = decryptor.update(chunk)
                if unpadder is not None:
                    clear = unpadder.update(clear)
                if clear:
                    target.write(clear)
                    out256.update(clear)
                    out512.update(clear)
                    output_bytes += len(clear)

            final = decryptor.finalize()
            if unpadder is not None:
                final = unpadder.update(final) + unpadder.finalize()
            if final:
                target.write(final)
                out256.update(final)
                out512.update(final)
                output_bytes += len(final)
            target.flush()
            os.fsync(target.fileno())
        partial.replace(output_path)
    except Exception:
        # Keep no ambiguous plaintext artifact after a failed transform.
        if partial.exists():
            partial.unlink()
        raise

    receipt = DecryptionReceipt(
        algorithm="AES",
        mode=mode,
        padding=padding_mode,
        input_path=input_path,
        output_path=output_path,
        input_bytes=input_size,
        output_bytes=output_bytes,
        input_sha256=in256.hexdigest(),
        input_sha512=in512.hexdigest(),
        output_sha256=out256.hexdigest(),
        output_sha512=out512.hexdigest(),
        key_fingerprint_sha256=key_material.fingerprint_sha256,
        key_bits=len(key_material.key) * 8,
        key_source_label=key_material.source_label,
        iv_hex=iv.hex(),
    )
    if receipt_path is not None:
        receipt.write_json(receipt_path)
    return receipt
