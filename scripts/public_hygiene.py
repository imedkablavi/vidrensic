from __future__ import annotations

import re
import subprocess
from pathlib import Path


TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".toml",
    ".yml",
    ".yaml",
    ".json",
    ".txt",
    ".cff",
    ".sh",
}

# Fail closed for file types that commonly contain recorder/case evidence. A
# deliberately redistributable synthetic binary fixture must be reviewed and
# added to PUBLIC_EVIDENCE_ALLOWLIST by exact repository path rather than
# weakening the suffix policy globally.
EVIDENCE_SUFFIXES = {
    ".raw",
    ".img",
    ".dd",
    ".e01",
    ".ex01",
    ".aff4",
    ".map",
    ".dav",
    ".dhav",
    ".mp4",
    ".h264",
    ".h265",
    ".hevc",
    ".264",
    ".265",
}
PUBLIC_EVIDENCE_ALLOWLIST: frozenset[str] = frozenset()
SENSITIVE_ROOT_PREFIXES = ("cases/", "case/", "evidence/", "acquisitions/")

SECRET_PATTERNS = {
    "PEM private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "credential URL": re.compile(r"https?://[^\s/:]+:[^\s/@]+@"),
    "likely local case path": re.compile(
        r"/(?:home|srv|mnt)/[^\s'\"`]+/(?:case|cases|evidence|recovery|recoveries)[^\s'\"`]*",
        re.IGNORECASE,
    ),
}

SKIP_PREFIXES = (".git/", "dist/", "build/", ".venv/", "venv/")


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        stdout=subprocess.PIPE,
    )
    return [Path(item.decode()) for item in result.stdout.split(b"\0") if item]


def path_policy_findings(path: Path) -> list[str]:
    text = path.as_posix()
    findings: list[str] = []
    if text.startswith(SENSITIVE_ROOT_PREFIXES):
        findings.append(f"{path}: tracked path is inside a case/evidence root")
    if path.suffix.lower() in EVIDENCE_SUFFIXES and text not in PUBLIC_EVIDENCE_ALLOWLIST:
        findings.append(
            f"{path}: tracked forensic/media evidence suffix {path.suffix!r} is not explicitly allowlisted"
        )
    return findings


def should_scan(path: Path) -> bool:
    text = path.as_posix()
    if text.startswith(SKIP_PREFIXES):
        return False
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {
        "LICENSE",
        "NOTICE",
        "AUTHORS",
        "SECURITY",
    }


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        findings.extend(path_policy_findings(path))
        if not should_scan(path) or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{path}: possible {name}")

    if findings:
        print("Public-release hygiene check FAILED:")
        for finding in findings:
            print(f" - {finding}")
        return 1

    print("Public-release hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
