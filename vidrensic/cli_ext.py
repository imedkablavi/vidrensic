from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

from vidrensic import __product__, __version__
from vidrensic.acquisition.ddrescue import AcquisitionPlan
from vidrensic.acquisition.linux import require_safe_source
from vidrensic.acquisition.receipt import build_acquisition_receipt
from vidrensic.cli import main as legacy_main
from vidrensic.core.case import Case
from vidrensic.core.doctor import run_doctor
from vidrensic.core.units import parse_byte_size
from vidrensic.crypto import KeyMaterial, decrypt_aes_file


EXTENDED_COMMANDS = """
Extended 0.5 commands:
  doctor                 inspect forensic runtime/dependencies
  decrypt aes            audited known-key AES CBC/CTR transform
  acquire verify         verify ddrescue output/map and emit receipt
""".strip()


def _byte_size(value: str) -> int:
    try:
        return parse_byte_size(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _hex_bytes(value: str, *, expected: int | None = None) -> bytes:
    try:
        result = bytes.fromhex(value.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected hexadecimal bytes") from exc
    if expected is not None and len(result) != expected:
        raise argparse.ArgumentTypeError(f"expected exactly {expected} bytes")
    return result


def _doctor(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="vidrensic doctor")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run_doctor()
    data = report.to_dict()
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(f"{__product__} {__version__}")
        print(f"platform={data['platform']}")
        print(f"python={data['python']}")
        print(f"core_ready={str(data['core_ready']).lower()}")
        for tool in data["tools"]:
            state = "OK" if tool["available"] else "MISSING"
            version = f" — {tool['version']}" if tool["version"] else ""
            print(f"{state:7} {tool['name']:9} [{tool['capability']}]{version}")
    return 0 if report.core_ready else 2


def _decrypt_aes(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic decrypt aes",
        description="Audited known-key AES transform; no key discovery or brute force.",
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("cbc", "ctr"), required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--key-encoding", choices=("raw", "hex"), default="raw")
    parser.add_argument("--iv-hex", required=True)
    parser.add_argument("--padding", choices=("none", "pkcs7"), default="none")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--case", type=Path)
    args = parser.parse_args(argv)

    try:
        iv = _hex_bytes(args.iv_hex, expected=16)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    key = KeyMaterial.from_file(args.key_file, encoding=args.key_encoding)
    case = Case.load(args.case) if args.case else None
    details = {
        "input": str(args.input),
        "output": str(args.output),
        "mode": args.mode,
        "padding": args.padding,
        "receipt": str(args.receipt),
        "key_source_label": key.source_label,
        "key_fingerprint_sha256": key.fingerprint_sha256,
        "iv_hex": iv.hex(),
    }
    job = None
    if case:
        job = case.jobs.create("crypto.decrypt.aes", details)
        case.jobs.start(job.job_id)
        case.audit.append(
            "crypto.decrypt.started",
            {**details, "job_id": job.job_id},
            actor=case.examiner,
        )
    try:
        receipt = decrypt_aes_file(
            args.input,
            args.output,
            key_material=key,
            iv=iv,
            mode=args.mode,
            padding_mode=args.padding,
            receipt_path=args.receipt,
        )
    except Exception as exc:
        if case and job:
            case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
            case.audit.append(
                "crypto.decrypt.failed",
                {**details, "job_id": job.job_id, "error": f"{type(exc).__name__}: {exc}"},
                actor=case.examiner,
            )
        raise

    if case and job:
        case.jobs.checkpoint(
            job.job_id,
            {
                "output_sha256": receipt.output_sha256,
                "output_bytes": receipt.output_bytes,
                "receipt": str(args.receipt),
            },
        )
        case.jobs.complete(job.job_id)
        case.audit.append(
            "crypto.decrypt.finished",
            {
                **details,
                "job_id": job.job_id,
                "input_sha256": receipt.input_sha256,
                "output_sha256": receipt.output_sha256,
                "output_bytes": receipt.output_bytes,
            },
            actor=case.examiner,
        )
    print(args.receipt.expanduser().resolve())
    return 0


def _acquire_verify(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic acquire verify",
        description="Verify a ddrescue acquisition/map and produce a forensic receipt.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--map", dest="mapfile", type=Path, required=True)
    parser.add_argument("--offset", type=_byte_size, default=0)
    parser.add_argument("--size", type=_byte_size)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--return-code", type=int, action="append", default=[])
    parser.add_argument("--skip-output-hash", action="store_true")
    parser.add_argument("--case", type=Path)
    args = parser.parse_args(argv)

    source_info = require_safe_source(args.source)
    plan = AcquisitionPlan(
        source=args.source,
        output=args.output,
        mapfile=args.mapfile,
        offset=args.offset,
        size=args.size,
    )
    receipt = build_acquisition_receipt(
        plan,
        source_info,
        tuple(args.return_code),
        hash_output=not args.skip_output_hash,
    )
    receipt.write_json(args.receipt)

    if args.case:
        case = Case.load(args.case)
        case.audit.append(
            "acquisition.verified",
            {
                "source": str(args.source),
                "output": str(args.output),
                "mapfile": str(args.mapfile),
                "receipt": str(args.receipt),
                "status": receipt.status,
                "reasons": list(receipt.reasons),
                "output_sha256": receipt.output_sha256,
                "map_sha256": receipt.map_sha256,
            },
            actor=case.examiner,
        )
    print(f"status={receipt.status}")
    print(args.receipt.expanduser().resolve())
    return 0 if receipt.status == "COMPLETE" else 3


def _extended_help() -> int:
    # Preserve the established CLI help while making new commands discoverable.
    try:
        legacy_main(["--help"])
    except SystemExit:
        pass
    print()
    print(EXTENDED_COMMANDS)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return _extended_help()
    if args == ["--help"] or args == ["-h"]:
        return _extended_help()
    if args[0] == "doctor":
        return _doctor(args[1:])
    if args[:2] == ["decrypt", "aes"]:
        return _decrypt_aes(args[2:])
    if args[:2] == ["acquire", "verify"]:
        return _acquire_verify(args[2:])
    return legacy_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
