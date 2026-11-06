"""Shared helpers: input scanning and JSON equality keys."""

from __future__ import annotations

import math
from collections.abc import Hashable
from typing import Any

from schema_compat.errors import SchemaCompatError

DEFAULT_MAX_DEPTH = 64


def scan_value(value: Any, max_depth: int = DEFAULT_MAX_DEPTH) -> None:
    """Check ``value`` is plain JSON data nested at most ``max_depth`` containers deep.

    The walk is iterative, so hostile nesting can never exhaust the interpreter stack.

    Raises:
        SchemaCompatError: ``too_deep`` when nesting is deeper than ``max_depth``;
            ``invalid_schema`` for values that JSON cannot represent.
    """
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, dict | list):
            depth += 1
            if depth > max_depth:
                raise SchemaCompatError("too_deep", f"nesting is deeper than {max_depth} levels")
            children: list[Any]
            if isinstance(node, dict):
                if not all(isinstance(key, str) for key in node):
                    raise SchemaCompatError("invalid_schema", "object keys must be strings")
                children = list(node.values())
            else:
                children = node
            stack.extend((child, depth) for child in children)
        elif isinstance(node, float) and not math.isfinite(node):
            raise SchemaCompatError("invalid_schema", "numbers must be finite")
        elif node is not None and not isinstance(node, bool | int | float | str):
            raise SchemaCompatError("invalid_schema", "value is not JSON data")


def canon(value: Any) -> Hashable:
    """Return a hashable key such that two keys are equal iff the JSON values are equal.

    Integers and floats compare numerically (``1`` equals ``1.0``), booleans only equal
    booleans, arrays compare by order and objects by keys and values.
    """
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int | float):
        return ("num", value)
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, list):
        return ("arr", tuple(canon(item) for item in value))
    if isinstance(value, dict):
        return ("obj", frozenset((key, canon(item)) for key, item in value.items()))
    raise SchemaCompatError("invalid_schema", "value is not JSON data")
