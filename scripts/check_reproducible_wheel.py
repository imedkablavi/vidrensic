from __future__ import annotations

import argparse
from hashlib import sha256
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory


EXPECTED_TOOLS = {
    "build": "1.5.0",
    "setuptools": "84.0.0",
    "wheel": "0.48.0",
}


def _digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def _git_text(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    return proc.stdout.strip()


def _verify_tools() -> dict[str, str]:
    observed: dict[str, str] = {}
    for package, expected in EXPECTED_TOOLS.items():
        version = metadata.version(package)
        observed[package] = version
        if version != expected:
            raise RuntimeError(
                f"reproducibility environment mismatch: {package}={version}, expected {expected}"
            )
    return observed


def _archive_source(repo: Path, archive: Path) -> None:
    with archive.open("wb") as handle:
        subprocess.run(
            ["git", "archive", "--format=tar", "HEAD"],
            cwd=repo,
            stdout=handle,
            timeout=30,
            check=True,
        )


def _extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, "r") as bundle:
        # The archive is generated from the current trusted Git tree, but use
        # the data filter as defense-in-depth against path/device entries.
        bundle.extractall(destination, filter="data")


def _build_wheel(source: Path, output: Path, env: dict[str, str]) -> Path:
    output.mkdir(parents=True, exist_ok=False)
    _run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(output),
            str(source),
        ],
        env=env,
    )
    wheels = sorted(output.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected exactly one wheel, found {len(wheels)} in {output}")
    return wheels[0]


def check_reproducible_wheel(
    repo: Path,
    *,
    report_path: Path,
    reference_wheel: Path | None = None,
) -> dict:
    repo = repo.expanduser().resolve()
    report_path = report_path.expanduser().resolve()
    tools = _verify_tools()
    commit = _git_text(repo, "rev-parse", "HEAD")
    source_date_epoch_text = _git_text(repo, "show", "-s", "--format=%ct", "HEAD")
    source_date_epoch = int(source_date_epoch_text)
    if source_date_epoch <= 0:
        raise RuntimeError("commit timestamp is not a positive SOURCE_DATE_EPOCH")

    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = str(source_date_epoch)
    env["PYTHONHASHSEED"] = "0"

    with TemporaryDirectory(prefix="vidrensic-repro-wheel-") as temp_name:
        temp = Path(temp_name)
        archive = temp / "source.tar"
        _archive_source(repo, archive)
        source_a = temp / "source-a"
        source_b = temp / "source-b"
        _extract(archive, source_a)
        _extract(archive, source_b)
        wheel_a = _build_wheel(source_a, temp / "dist-a", env)
        wheel_b = _build_wheel(source_b, temp / "dist-b", env)

        digest_a = _digest(wheel_a)
        digest_b = _digest(wheel_b)
        same_name = wheel_a.name == wheel_b.name
        reproducible = same_name and digest_a == digest_b

        reference = None
        if reference_wheel is not None:
            reference_wheel = reference_wheel.expanduser().resolve()
            if not reference_wheel.is_file():
                raise FileNotFoundError(reference_wheel)
            reference_digest = _digest(reference_wheel)
            reference = {
                "path": str(reference_wheel),
                "filename": reference_wheel.name,
                "sha256": reference_digest,
                "matches_rebuild": (
                    reference_wheel.name == wheel_a.name and reference_digest == digest_a
                ),
            }
            reproducible = reproducible and bool(reference["matches_rebuild"])

        report = {
            "schema_version": 1,
            "artifact": "reproducible-wheel-qualification",
            "commit": commit,
            "source_date_epoch": source_date_epoch,
            "python": sys.version.split()[0],
            "build_tools": tools,
            "build_a": {"filename": wheel_a.name, "sha256": digest_a},
            "build_b": {"filename": wheel_b.name, "sha256": digest_b},
            "reference": reference,
            "reproducible": reproducible,
            "claim_limit": (
                "Byte-for-byte reproducibility is established only for the wheel under this pinned "
                "Python/build-tool environment and exact source commit. The sdist is not covered."
            ),
        }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_name(report_path.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(report_path)
    if not report["reproducible"]:
        raise RuntimeError("wheel reproducibility check failed; see report for compared digests")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify byte-for-byte reproducible Vidrensic wheel builds")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reference-wheel", type=Path)
    args = parser.parse_args()
    report = check_reproducible_wheel(
        args.repo,
        report_path=args.out,
        reference_wheel=args.reference_wheel,
    )
    print(f"reproducible={str(report['reproducible']).lower()}")
    print(args.out.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
