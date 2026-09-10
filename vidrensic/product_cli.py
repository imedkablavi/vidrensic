from __future__ import annotations

import sys

from vidrensic import __product__, __version__
from vidrensic.cli import main as legacy_main
from vidrensic.cli_ext import main as extended_main
from vidrensic.ui import heading, label


PRODUCT_COMMANDS = (
    ("vidrensic analyze <source> --out <report>", "Analyze a recorder source"),
    ("vidrensic-media <artifact> --out <report>", "Inspect recovered video"),
    ("vidrensic-media <artifact> --out <report> --timeline", "Review video timing"),
    ("vidrensic-media <artifact> --out <report> --decoder-errors", "Map decoder-error regions"),
    ("vidrensic-scenes <artifact> --out <sheet.png>", "Create visual contact sheet"),
    ("vidrensic-duplicates <a> <b> --out <report>", "Find duplicate video candidates"),
    ("vidrensic-export <artifact> --out <copy> --manifest <report>", "Create a verified copy"),
    ("vidrensic-profiler <source> --out <bundle>", "Prepare a support bundle"),
    ("vidrensic doctor", "Check system readiness"),
)

ADVANCED_COMMANDS = (
    "vidrensic analyze <source> --out <report>",
    "vidrensic-media <artifact> --out <report> [--timeline] [--decoder-errors] [--qc fast|full]",
    "vidrensic-scenes <artifact> --out <sheet.png> [--samples 24] [--thumb-width 320]",
    "vidrensic-duplicates <source>... --out <report> [--samples 32] [--threshold 0.90]",
    "vidrensic-export <artifact> --out <copy> --manifest <report>",
    "vidrensic-profiler <source> --out <bundle> [--json]",
    "vidrensic acquire verify <source> --output <image> --map <map> --receipt <report>",
    "vidrensic recover wfs <source> --starts <n,...> --stop-fragment <n> --out <dir> --label <name>",
    "vidrensic validate corpus <manifest> --out <report>",
    "vidrensic validate private-case <source> --out <manifest> --case-id <id> --family <family>",
)


def _product_help() -> int:
    heading("Vidrensic", f"{__product__} {__version__} · Forensic video evidence")
    print("Start here")
    print()
    for command, description in PRODUCT_COMMANDS:
        print(f"  {command:<64} {description}")
    print()
    label("More", "vidrensic --advanced-help")
    return 0


def _advanced_help() -> int:
    try:
        legacy_main(["--help"])
    except SystemExit:
        pass
    print()
    heading("Advanced commands")
    for command in ADVANCED_COMMANDS:
        print(f"  {command}")
    print()
    label("Product help", "vidrensic --help")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args in (["--help"], ["-h"]):
        return _product_help()
    if args == ["--advanced-help"]:
        return _advanced_help()
    return extended_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
