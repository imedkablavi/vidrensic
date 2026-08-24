from __future__ import annotations

import argparse
import os
from pathlib import Path

from packaging.version import InvalidVersion, Version

from vidrensic import __version__
from vidrensic.core.json_limits import BoundedJSONError, load_bounded_json
from vidrensic.validation.real_corpus import RealCorpusIndexError, validate_real_corpus_index


MAX_REAL_CORPUS_INDEX_BYTES = 8 * 1024 * 1024


class ReleaseTagPolicyError(ValueError):
    pass


def _load_real_index(path: Path) -> dict:
    try:
        data = load_bounded_json(
            path,
            max_bytes=MAX_REAL_CORPUS_INDEX_BYTES,
            max_depth=48,
            max_nodes=250_000,
            max_string_chars=64 * 1024,
            label="real-recorder corpus index",
        )
    except BoundedJSONError as exc:
        raise ReleaseTagPolicyError(str(exc)) from exc
    try:
        validate_real_corpus_index(data)
    except RealCorpusIndexError as exc:
        raise ReleaseTagPolicyError(str(exc)) from exc
    if not isinstance(data, dict):
        raise ReleaseTagPolicyError("real-recorder corpus index must be an object")
    return data


def evaluate_release_tag_policy(
    *,
    ref_name: str,
    ref_type: str,
    package_version: str,
    real_index_path: Path,
) -> dict[str, object]:
    """Return release-channel facts or raise when automated publication policy fails.

    Branch/workflow-dispatch qualification is deliberately allowed without a
    release tag. Tag publication requires exact package-version agreement.
    Prerelease/dev tags can qualify with an empty real-recorder corpus, but a
    stable tag cannot be published while the admitted real-recorder index has
    zero cases.

    A non-empty real index is only a minimum automated stable-release gate. It
    does not satisfy the separate manual/legal/lab release gates documented in
    RELEASE_QUALIFICATION.md.
    """

    if ref_type != "tag":
        return {
            "mode": "qualification-only",
            "ref_name": ref_name,
            "ref_type": ref_type,
            "package_version": package_version,
            "release_channel": None,
            "real_case_count": None,
        }

    if not ref_name.startswith("v") or len(ref_name) == 1:
        raise ReleaseTagPolicyError("release tag must use the v<version> form")

    try:
        tag_version = Version(ref_name[1:])
        installed_version = Version(package_version)
    except InvalidVersion as exc:
        raise ReleaseTagPolicyError(f"invalid release/package version: {exc}") from exc

    if tag_version != installed_version:
        raise ReleaseTagPolicyError(
            f"release tag {ref_name} does not match package version {package_version}"
        )

    data = _load_real_index(real_index_path)
    cases = data.get("cases")
    if not isinstance(cases, list):
        # validate_real_corpus_index() already enforces this; retain an explicit
        # invariant here so policy logic never guesses about an unexpected type.
        raise ReleaseTagPolicyError("real-recorder corpus cases must be a list")

    prerelease = tag_version.is_prerelease or tag_version.is_devrelease
    channel = "prerelease" if prerelease else "stable"
    if not prerelease and not cases:
        raise ReleaseTagPolicyError(
            "stable release tag is blocked: the admitted real-recorder corpus contains zero cases"
        )

    return {
        "mode": "tag-publication",
        "ref_name": ref_name,
        "ref_type": ref_type,
        "package_version": str(installed_version),
        "release_channel": channel,
        "real_case_count": len(cases),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enforce Vidrensic release tag/version and minimum real-corpus policy"
    )
    parser.add_argument("--ref-name", default=os.environ.get("GITHUB_REF_NAME", ""))
    parser.add_argument("--ref-type", default=os.environ.get("GITHUB_REF_TYPE", ""))
    parser.add_argument("--package-version", default=__version__)
    parser.add_argument(
        "--real-index",
        type=Path,
        default=Path("validation_corpus/real/real-corpus-index.json"),
    )
    args = parser.parse_args()

    try:
        result = evaluate_release_tag_policy(
            ref_name=args.ref_name,
            ref_type=args.ref_type,
            package_version=args.package_version,
            real_index_path=args.real_index,
        )
    except ReleaseTagPolicyError as exc:
        parser.error(str(exc))

    fields = " ".join(f"{key}={value}" for key, value in result.items())
    print(f"release tag policy passed: {fields}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
