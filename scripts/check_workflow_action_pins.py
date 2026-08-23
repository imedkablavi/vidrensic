from __future__ import annotations

from pathlib import Path
import re


WORKFLOW_ROOT = Path(".github/workflows")
USES_RE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def check_workflow(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    for match in USES_RE.finditer(text):
        value = match.group(1)
        if value.startswith("./"):
            continue
        if "@" not in value:
            errors.append(f"{path}: external action has no immutable ref: {value}")
            continue
        action, ref = value.rsplit("@", 1)
        if not action or not FULL_SHA_RE.fullmatch(ref):
            errors.append(f"{path}: external action must use a full 40-hex commit SHA: {value}")
    return errors


def main() -> int:
    workflows = sorted((*WORKFLOW_ROOT.glob("*.yml"), *WORKFLOW_ROOT.glob("*.yaml")))
    if not workflows:
        print("no workflow files found")
        return 1

    errors: list[str] = []
    for path in workflows:
        errors.extend(check_workflow(path))

    if errors:
        for error in errors:
            print(error)
        return 1

    print(f"validated immutable action pins in {len(workflows)} workflow file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
