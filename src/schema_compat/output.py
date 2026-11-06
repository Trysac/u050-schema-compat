"""Verdicts and rendering of change lists."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Literal

from schema_compat.models import Change, Severity


def is_compatible(changes: Sequence[Change], strict: bool = False) -> bool:
    """Return True when no change is breaking (and, if ``strict``, none is unknown)."""
    blocking = {Severity.BREAKING, Severity.UNKNOWN} if strict else {Severity.BREAKING}
    return all(change.severity not in blocking for change in changes)


def _line(change: Change) -> str:
    location = change.path or "(root)"
    return f"{change.severity.name} {location} {change.kind}: {change.detail}"


def render(changes: Sequence[Change], fmt: Literal["text", "json"]) -> str:
    """Render changes as text lines or as a JSON array sorted by ``(path, kind)``.

    Text lines look like ``<SEVERITY> <path> <kind>: <detail>``. JSON objects have the keys
    ``path``, ``kind``, ``severity``, ``direction`` and ``detail``.

    Raises:
        ValueError: when ``fmt`` is neither ``text`` nor ``json``.
    """
    if fmt == "text":
        return "\n".join(_line(change) for change in changes)
    if fmt == "json":
        rows = sorted(changes, key=lambda change: (change.path, change.kind))
        payload = [
            {
                "path": change.path,
                "kind": change.kind,
                "severity": change.severity.name,
                "direction": change.direction,
                "detail": change.detail,
            }
            for change in rows
        ]
        return json.dumps(payload, indent=2)
    raise ValueError("fmt must be 'text' or 'json'")
