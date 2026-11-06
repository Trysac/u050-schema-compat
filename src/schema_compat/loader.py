"""Loading schemas from disk with size and depth limits."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from schema_compat._common import DEFAULT_MAX_DEPTH, scan_value
from schema_compat.errors import SchemaCompatError

DEFAULT_MAX_BYTES = 10_000_000


def _reject_constant(name: str) -> Any:
    raise ValueError("non-finite number")


def _parse_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("non-finite number")
    return value


def load_schema(
    path: Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> dict[str, Any] | bool:
    """Read a JSON Schema document (an object or a boolean) from ``path``.

    Args:
        path: File to read, UTF-8 encoded JSON.
        max_bytes: Largest accepted file size in bytes.
        max_depth: Largest accepted nesting depth of arrays and objects.

    Raises:
        SchemaCompatError: ``input_too_large``, ``invalid_json``, ``too_deep`` or
            ``invalid_schema`` (the document is neither an object nor a boolean).
        OSError: when the file cannot be read.
        ValueError: when a limit argument is out of range.
    """
    if max_bytes < 0 or max_depth < 1:
        raise ValueError("max_bytes must be >= 0 and max_depth must be >= 1")
    with Path(path).open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise SchemaCompatError("input_too_large", f"schema file exceeds {max_bytes} bytes")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SchemaCompatError("invalid_json", "schema file is not valid UTF-8") from None
    try:
        data = json.loads(text, parse_constant=_reject_constant, parse_float=_parse_float)
    except RecursionError:
        raise SchemaCompatError("too_deep", "JSON nesting is too deep to parse") from None
    except json.JSONDecodeError as exc:
        message = f"invalid JSON at line {exc.lineno} column {exc.colno}"
        raise SchemaCompatError("invalid_json", message) from None
    except ValueError:
        raise SchemaCompatError("invalid_json", "invalid JSON value") from None
    scan_value(data, max_depth)
    if not isinstance(data, dict | bool):
        raise SchemaCompatError("invalid_schema", "a schema must be an object or a boolean")
    return data
