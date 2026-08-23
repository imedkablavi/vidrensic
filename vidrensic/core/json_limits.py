from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import stat


class BoundedJSONError(ValueError):
    pass


def _validate_shape(
    value: Any,
    *,
    max_depth: int,
    max_nodes: int,
    max_string_chars: int,
) -> None:
    stack: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            raise BoundedJSONError(f"JSON structure exceeds {max_nodes} nodes")
        if depth > max_depth:
            raise BoundedJSONError(f"JSON structure exceeds maximum depth {max_depth}")

        if isinstance(current, str):
            if len(current) > max_string_chars:
                raise BoundedJSONError(
                    f"JSON string exceeds {max_string_chars} characters"
                )
            continue
        if isinstance(current, dict):
            for key, child in current.items():
                if not isinstance(key, str):
                    raise BoundedJSONError("JSON object key is not a string")
                if len(key) > max_string_chars:
                    raise BoundedJSONError(
                        f"JSON object key exceeds {max_string_chars} characters"
                    )
                stack.append((child, depth + 1))
            continue
        if isinstance(current, list):
            stack.extend((child, depth + 1) for child in current)


def load_bounded_json(
    path: Path,
    *,
    max_bytes: int,
    max_depth: int = 32,
    max_nodes: int = 100_000,
    max_string_chars: int = 64 * 1024,
    label: str = "JSON file",
) -> Any:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if max_depth < 1:
        raise ValueError("max_depth must be positive")
    if max_nodes < 1:
        raise ValueError("max_nodes must be positive")
    if max_string_chars < 1:
        raise ValueError("max_string_chars must be positive")

    resolved = path.expanduser().resolve()
    try:
        mode = resolved.stat().st_mode
    except FileNotFoundError:
        raise
    if not stat.S_ISREG(mode):
        raise BoundedJSONError(f"{label} must be a regular file")

    with resolved.open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise BoundedJSONError(f"{label} exceeds maximum size of {max_bytes} bytes")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BoundedJSONError(f"{label} is not valid UTF-8") from exc

    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BoundedJSONError(f"{label} is not valid JSON: {exc.msg}") from exc
    except RecursionError as exc:
        raise BoundedJSONError(f"{label} JSON nesting exceeds parser limits") from exc

    _validate_shape(
        value,
        max_depth=max_depth,
        max_nodes=max_nodes,
        max_string_chars=max_string_chars,
    )
    return value
