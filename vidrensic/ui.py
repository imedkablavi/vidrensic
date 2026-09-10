from __future__ import annotations

from pathlib import Path
import os
import sys


_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"


def _supports_color() -> bool:
    return bool(sys.stdout.isatty() and os.environ.get("TERM") not in {None, "dumb"} and "NO_COLOR" not in os.environ)


def _paint(code: str, text: str) -> str:
    return f"{code}{text}{_RESET}" if _supports_color() else text


def heading(title: str, subtitle: str | None = None) -> None:
    print(_paint(_BOLD, title))
    if subtitle:
        print(_paint(_DIM, subtitle))
    print()


def success(message: str) -> None:
    print(_paint(_GREEN, message))


def warning(message: str) -> None:
    print(_paint(_YELLOW, message))


def error(message: str) -> None:
    print(_paint(_RED, message), file=sys.stderr)


def label(name: str, value: object) -> None:
    print(f"{_paint(_DIM, name):<18} {value}")


def path(label_name: str, value: Path) -> None:
    label(label_name, value.expanduser().resolve())


def divider() -> None:
    print(_paint(_DIM, "─" * 56))


def confidence_label(value: float | None) -> str:
    if value is None:
        return "Unknown"
    if value >= 0.85:
        return "High"
    if value >= 0.65:
        return "Moderate"
    return "Low"


def review_label(requires_review: bool) -> str:
    return "Review required" if requires_review else "Ready for next step"


def human_size(value: int | None) -> str:
    if value is None:
        return "Unknown"
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount)} {unit}"
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"


def detection_name(plugin: str | None) -> str:
    names = {
        "wfs": "WFS",
        "dhav": "DHAV",
        "hikvision": "Hikvision",
        "annexb": "H.264 / H.265 stream",
        "mpegps": "MPEG program stream",
    }
    if plugin is None:
        return "No clear match"
    return names.get(plugin, plugin.replace("_", " ").title())
