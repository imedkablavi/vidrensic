from __future__ import annotations

import argparse
from pathlib import Path

from cvf import __version__
from cvf.acquisition.linux import inspect_source
from cvf.core.case import Case


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cvf", description="Cybrex Video Forensics")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command")

    case = sub.add_parser("case")
    case_sub = case.add_subparsers(dest="case_command")
    create = case_sub.add_parser("create")
    create.add_argument("case_id")
    create.add_argument("--root", type=Path, required=True)

    source = sub.add_parser("source")
    source_sub = source.add_subparsers(dest="source_command")
    inspect = source_sub.add_parser("inspect")
    inspect.add_argument("path", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "case" and args.case_command == "create":
        case = Case.create(args.root, args.case_id)
        print(case.root)
        return 0
    if args.command == "source" and args.source_command == "inspect":
        info = inspect_source(args.path)
        print(f"path={info.path}")
        print(f"block_device={info.is_block_device}")
        print(f"read_only={info.read_only}")
        print(f"size_bytes={info.size_bytes}")
        return 0
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
