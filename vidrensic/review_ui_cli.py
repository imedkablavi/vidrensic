from __future__ import annotations

import argparse
from pathlib import Path
import sys
import threading
import webbrowser

from vidrensic.core.case import Case
from vidrensic.review_server import LOOPBACK_HOSTS, serve_review_workstation
from vidrensic.review_ui_v3 import REVIEW_WORKSTATION_HTML


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected port number") from exc
    if not 0 < port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic-review-ui",
        description="Launch the local Vidrensic graphical review workstation.",
    )
    parser.add_argument("--case", type=Path, required=True, help="case directory")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=_port, default=8765)
    parser.add_argument("--allow-network", action="store_true", help="allow a non-loopback bind")
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args(argv)

    try:
        case = Case.load(args.case)
        if args.host.strip() not in LOOPBACK_HOSTS and not args.allow_network:
            parser.error("non-loopback review server requires --allow-network")
        if args.open_browser:
            # Start the server in this process, then ask the browser to open the fixed local URL.
            def open_browser() -> None:
                webbrowser.open(f"http://{args.host}:{args.port}/")

            timer = threading.Timer(0.25, open_browser)
            timer.daemon = True
            timer.start()
        print(f"Vidrensic Review Workstation: http://{args.host}:{args.port}/")
        print(f"Case: {case.root}")
        print("Press Ctrl+C to stop.")
        serve_review_workstation(
            case,
            host=args.host,
            port=args.port,
            ui_html=REVIEW_WORKSTATION_HTML,
            allow_network=args.allow_network,
        )
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Unable to start review workstation: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
