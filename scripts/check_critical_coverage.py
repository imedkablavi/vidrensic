from __future__ import annotations

from pathlib import Path
import argparse
import sys
import xml.etree.ElementTree as ET


DEFAULT_THRESHOLDS = {
    "plugins/wfs/reconstruct.py": 80.0,
    "plugins/wfs/global_reconstruct.py": 85.0,
    "plugins/wfs/recovery.py": 85.0,
    "recovery/solver.py": 90.0,
    "core/hashing.py": 90.0,
    "core/provenance.py": 90.0,
    "crypto/decrypt.py": 80.0,
    "acquisition/ddrescue.py": 75.0,
}


def read_rates(path: Path) -> tuple[float, dict[str, float]]:
    root = ET.parse(path).getroot()
    overall = float(root.attrib.get("line-rate", "0")) * 100.0
    rates: dict[str, float] = {}
    for cls in root.findall(".//class"):
        filename = cls.attrib.get("filename")
        if filename:
            rates[filename] = float(cls.attrib.get("line-rate", "0")) * 100.0
    return overall, rates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enforce coverage on forensic-critical modules")
    parser.add_argument("coverage_xml", type=Path)
    parser.add_argument("--overall", type=float, default=80.0)
    args = parser.parse_args(argv)

    overall, rates = read_rates(args.coverage_xml)
    failures: list[str] = []
    print(f"overall coverage: {overall:.2f}% (required {args.overall:.2f}%)")
    if overall + 1e-9 < args.overall:
        failures.append(f"overall coverage {overall:.2f}% < {args.overall:.2f}%")

    for filename, minimum in DEFAULT_THRESHOLDS.items():
        actual = rates.get(filename)
        if actual is None:
            failures.append(f"critical module missing from coverage report: {filename}")
            print(f"MISSING {filename} (required {minimum:.2f}%)")
            continue
        state = "PASS" if actual + 1e-9 >= minimum else "FAIL"
        print(f"{state:4} {filename}: {actual:.2f}% (required {minimum:.2f}%)")
        if state == "FAIL":
            failures.append(f"{filename} {actual:.2f}% < {minimum:.2f}%")

    if failures:
        print("coverage gate failed:", file=sys.stderr)
        for item in failures:
            print(f"- {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
