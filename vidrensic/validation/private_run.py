from __future__ import annotations

from pathlib import Path
from typing import Any
import os

from vidrensic.core.private_io import atomic_write_private_json
from vidrensic.validation.corpus import CorpusRunReport, ValidationCorpus, load_corpus, run_corpus


REAL_PROVENANCE = frozenset({"public", "lab", "restricted"})


class PrivateValidationError(ValueError):
    """Raised when a restricted validation run would violate safety policy."""


def _git_root(path: Path) -> Path | None:
    current = path.expanduser().resolve()
    if not current.exists():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _assert_outside_git(path: Path, label: str) -> None:
    root = _git_root(path)
    if root is not None:
        raise PrivateValidationError(
            f"{label} is inside a Git working tree; move private validation data outside source control: {path}"
        )


def _assert_real_corpus(corpus: ValidationCorpus) -> None:
    synthetic = [case.case_id for case in corpus.cases if case.provenance == "synthetic"]
    unsupported = [
        f"{case.case_id}:{case.provenance}"
        for case in corpus.cases
        if case.provenance not in REAL_PROVENANCE
    ]
    if synthetic:
        raise PrivateValidationError(
            "private real-recorder validation rejects synthetic cases: " + ", ".join(synthetic)
        )
    if unsupported:
        raise PrivateValidationError(
            "private real-recorder validation found unsupported provenance: "
            + ", ".join(unsupported)
        )


def run_private_corpus(
    manifest: Path,
    output: Path,
    *,
    allow_git_paths: bool = False,
) -> CorpusRunReport:
    """Run a non-synthetic corpus and write its report with owner-only permissions.

    The manifest and all fixture sources must be outside any Git working tree by
    default. This prevents a private report or active-case manifest from being
    accidentally committed to a public repository. Set ``allow_git_paths`` only
    when an organization has explicitly chosen a controlled private repository.

    No evidence is copied by the runner. Recovery products created by the corpus
    engine remain temporary and are removed by its existing per-expectation
    lifecycle.
    """

    manifest = manifest.expanduser().resolve()
    output = output.expanduser().resolve()
    if not manifest.is_file() or manifest.is_symlink():
        raise PrivateValidationError("manifest must be an existing regular non-symlink file")
    if manifest == output:
        raise PrivateValidationError("private validation report must differ from the manifest path")
    if output.exists() and output.is_symlink():
        raise PrivateValidationError("private validation report may not be a symlink")

    corpus = load_corpus(manifest)
    _assert_real_corpus(corpus)

    if not allow_git_paths:
        _assert_outside_git(manifest, "validation manifest")
        _assert_outside_git(output, "validation report")
        for case in corpus.cases:
            _assert_outside_git(case.source, f"fixture source for {case.case_id}")

    report = run_corpus(corpus)
    atomic_write_private_json(output, report.to_dict(), allow_replace=False)
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run restricted real-recorder validation outside source control and write a private report"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--allow-git-paths",
        action="store_true",
        help="allow a controlled private repository path; do not use for public repositories",
    )
    args = parser.parse_args(argv)

    try:
        report = run_private_corpus(
            args.manifest,
            args.out,
            allow_git_paths=args.allow_git_paths,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    print(f"status={report.status}")
    print(f"passed={report.passed}")
    print(f"failed={report.failed}")
    print(f"report={args.out.expanduser().resolve()}")
    return 0 if report.status == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
