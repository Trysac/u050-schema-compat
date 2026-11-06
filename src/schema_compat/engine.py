"""Compatibility engine behind :func:`diff`.

The engine compares a reader schema with a writer schema. A finding is breaking when some
instance valid under the writer is invalid under the reader. BACKWARD uses reader=new and
writer=old, FORWARD swaps them and FULL merges both runs.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Hashable, Sequence
from dataclasses import replace
from typing import Any
from urllib.parse import unquote

from schema_compat._common import DEFAULT_MAX_DEPTH, canon, scan_value
from schema_compat.errors import SchemaCompatError, clip
from schema_compat.models import Change, Direction, Mode, Severity

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

_MAX_PAIRS = 100_000
_MAX_CHANGES = 100_000
_MAX_WALK_DEPTH = 128
_MAX_REF_HOPS = 64

_ALL_TYPES = frozenset({"array", "boolean", "integer", "null", "number", "object", "string"})
_ANNOTATIONS = frozenset(
    {
        "$anchor",
        "$comment",
        "$defs",
        "$id",
        "$schema",
        "$vocabulary",
        "default",
        "definitions",
        "deprecated",
        "description",
        "examples",
        "readOnly",
        "title",
        "writeOnly",
    }
)
_SUPPORTED = frozenset(
    {
        "$ref",
        "additionalProperties",
        "const",
        "enum",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "items",
        "maxItems",
        "maxLength",
        "maximum",
        "minItems",
        "minLength",
        "minimum",
        "properties",
        "required",
        "type",
    }
)
_BOUNDS: tuple[tuple[str, str | None, bool, bool], ...] = (
    ("minimum", "exclusiveMinimum", True, False),
    ("maximum", "exclusiveMaximum", False, False),
    ("minLength", None, True, True),
    ("maxLength", None, False, True),
    ("minItems", None, True, True),
    ("maxItems", None, False, True),
)
_RANK = {Severity.COMPATIBLE: 0, Severity.UNKNOWN: 1, Severity.BREAKING: 2}

_Bound = tuple[float, bool, str]
_Key = tuple[str, str, bool]


def _esc(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _unesc(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _q(text: str) -> str:
    return json.dumps(clip(text, 60))


def _higher(first: Severity, second: Severity) -> Severity:
    return first if _RANK[first] >= _RANK[second] else second


def _worst(changes: Sequence[Change]) -> Severity:
    result = Severity.COMPATIBLE
    for change in changes:
        result = _higher(result, change.severity)
    return result


def _brief(schema: Any) -> str:
    if isinstance(schema, bool):
        return "true" if schema else "false"
    return "an object schema"


def _require_schema(value: Any) -> None:
    if not isinstance(value, dict | bool):
        raise SchemaCompatError("invalid_schema", "a schema must be an object or a boolean")


def _is_index(name: str) -> bool:
    return name.isascii() and name.isdigit() and (name == "0" or not name.startswith("0"))


def _resolve_ref(ref: Any, root: Any) -> tuple[Any, str]:
    """Resolve a local ``$ref`` as an RFC 6901 pointer; return the target and its pointer."""
    if not isinstance(ref, str):
        raise SchemaCompatError("invalid_schema", "$ref must be a string")
    if ref != "#" and not ref.startswith("#/"):
        raise SchemaCompatError(
            "unsupported_ref",
            f"unsupported $ref {_q(ref)}: only local JSON pointers are supported",
        )
    try:
        decoded = unquote(ref[1:], errors="strict")
    except UnicodeDecodeError:
        raise SchemaCompatError("invalid_schema", f"$ref {_q(ref)} is not valid UTF-8") from None
    names = [_unesc(part) for part in decoded.split("/")[1:]]
    node = root
    for name in names:
        if isinstance(node, dict) and name in node:
            node = node[name]
        elif isinstance(node, list) and _is_index(name) and int(name) < len(node):
            node = node[int(name)]
        else:
            raise SchemaCompatError("invalid_schema", f"$ref {_q(ref)} does not resolve")
    return node, "".join(f"/{_esc(name)}" for name in names)


def _type_set(schema: dict[str, Any]) -> frozenset[str] | None:
    if "type" not in schema:
        return None
    raw = schema["type"]
    names = [raw] if isinstance(raw, str) else raw
    valid = isinstance(names, list) and len(names) > 0
    if not valid or not all(isinstance(name, str) and name in _ALL_TYPES for name in names):
        raise SchemaCompatError(
            "invalid_schema", "type must be a known type name or a non-empty list of them"
        )
    return frozenset(names)


def _expand(types: frozenset[str] | None) -> frozenset[str]:
    if types is None:
        return _ALL_TYPES
    if "number" in types:
        return types | {"integer"}
    return types


def _fmt_type(types: frozenset[str] | None) -> str:
    return "any" if types is None else "|".join(sorted(types))


def _allowed(schema: dict[str, Any]) -> dict[Hashable, Any] | None:
    """Return the effective set of allowed values from enum and const, or None for any."""
    values: dict[Hashable, Any] | None = None
    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, list):
            raise SchemaCompatError("invalid_schema", "enum must be an array")
        values = {canon(item): item for item in enum}
    if "const" in schema:
        const = schema["const"]
        key = canon(const)
        values = {key: const} if values is None or key in values else {}
    return values


def _show(values: dict[Hashable, Any] | None) -> str:
    if values is None:
        return "any value"
    return clip(json.dumps(list(values.values()), sort_keys=True, default=str), 80)


def _number(value: Any, keyword: str, integer: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SchemaCompatError("invalid_schema", f"{keyword} must be a number")
    if isinstance(value, float) and not math.isfinite(value):
        raise SchemaCompatError("invalid_schema", f"{keyword} must be finite")
    if integer and (value < 0 or (isinstance(value, float) and not value.is_integer())):
        raise SchemaCompatError("invalid_schema", f"{keyword} must be a non-negative integer")
    return value


def _bound(
    schema: dict[str, Any],
    inclusive: str,
    exclusive: str | None,
    lower: bool,
    integer: bool,
) -> _Bound | None:
    """Return the tightest bound (value, exclusive, keyword) declared by ``schema``."""
    candidates: list[_Bound] = []
    if inclusive in schema:
        candidates.append((_number(schema[inclusive], inclusive, integer), False, inclusive))
    if exclusive is not None and exclusive in schema:
        candidates.append((_number(schema[exclusive], exclusive, False), True, exclusive))
    if not candidates:
        return None
    sign = 1 if lower else -1
    return max(candidates, key=lambda item: (sign * item[0], item[1]))


def _bound_key(bound: _Bound | None, lower: bool) -> tuple[float, bool] | None:
    if bound is None:
        return None
    return ((1 if lower else -1) * bound[0], bound[1])


def _bound_text(bound: _Bound | None) -> str:
    return "none" if bound is None else f"{bound[2]} {bound[0]}"


def _properties(schema: dict[str, Any]) -> dict[str, Any]:
    value = schema.get("properties", {})
    if not isinstance(value, dict):
        raise SchemaCompatError("invalid_schema", "properties must be an object")
    return value


def _required(schema: dict[str, Any]) -> set[str]:
    value = schema.get("required", [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SchemaCompatError("invalid_schema", "required must be an array of strings")
    return set(value)


def _additional(schema: dict[str, Any]) -> Any:
    value = schema.get("additionalProperties", True)
    if not isinstance(value, dict | bool):
        raise SchemaCompatError(
            "invalid_schema", "additionalProperties must be a schema or a boolean"
        )
    return value


class _Walker:
    """Compares a reader schema against a writer schema and collects findings."""

    def __init__(self, reader_root: Any, writer_root: Any, swap: bool) -> None:
        self.reader_root = reader_root
        self.writer_root = writer_root
        self.swap = swap
        self.changes: list[Change] = []
        self.quiet = False
        self.memo: dict[_Key, Severity] = {}
        self.stack: set[_Key] = set()

    def _old_new(self, reader_value: Any, writer_value: Any) -> tuple[Any, Any]:
        if self.swap:
            return reader_value, writer_value
        return writer_value, reader_value

    def _emit(self, path: str, kind: str, severity: Severity, detail: str) -> None:
        if len(self.changes) >= _MAX_CHANGES:
            raise SchemaCompatError("too_complex", f"more than {_MAX_CHANGES} changes")
        self.changes.append(Change(path, kind, severity, None, detail))

    def _emit_schema_change(
        self, path: str, kind: str, reader: Any, writer: Any, severity: Severity
    ) -> None:
        old, new = self._old_new(reader, writer)
        detail = f"schema changed from {_brief(old)} to {_brief(new)}"
        self._emit(path, kind, severity, detail)

    def _emit_property(self, path: str, name: str, added: bool, severity: Severity) -> None:
        word = "added" if added else "removed"
        kind = "property_added" if added else "property_removed"
        self._emit(path, kind, severity, f"property {_q(name)} {word}")

    def _emit_required(self, path: str, name: str, added: bool, severity: Severity) -> None:
        kind = "required_added" if added else "required_removed"
        state = "is now required" if added else "is no longer required"
        self._emit(f"{path}/required", kind, severity, f"property {_q(name)} {state}")

    def _deref(self, schema: Any, pointer: str, root: Any) -> tuple[Any, str, dict[str, Any]]:
        """Follow ``$ref`` chains; return the target, its pointer and sibling keywords."""
        siblings: dict[str, Any] = {}
        for _ in range(_MAX_REF_HOPS):
            if not isinstance(schema, dict) or "$ref" not in schema:
                return schema, pointer, siblings
            extra = {k: v for k, v in schema.items() if k != "$ref" and k not in _ANNOTATIONS}
            siblings.update(extra)
            schema, pointer = _resolve_ref(schema["$ref"], root)
        raise SchemaCompatError("invalid_schema", "too many chained $ref hops")

    def _summarize(
        self,
        reader: Any,
        writer: Any,
        path: str,
        rptr: str,
        wptr: str,
        depth: int,
    ) -> Severity:
        """Compare two schemas and return only the worst severity, discarding the changes."""
        saved_changes, saved_quiet = self.changes, self.quiet
        self.changes, self.quiet = [], True
        try:
            return self.compare(reader, writer, path, rptr, wptr, depth)
        finally:
            self.changes, self.quiet = saved_changes, saved_quiet

    def compare(
        self,
        reader: Any,
        writer: Any,
        path: str,
        rptr: str,
        wptr: str,
        depth: int,
        bool_kind: str = "schema_changed",
    ) -> Severity:
        """Compare two schemas, append findings and return the worst severity found."""
        if depth > _MAX_WALK_DEPTH:
            raise SchemaCompatError("too_deep", "schema nesting exceeds the comparison limit")
        reader, rptr, reader_extra = self._deref(reader, rptr, self.reader_root)
        writer, wptr, writer_extra = self._deref(writer, wptr, self.writer_root)
        _require_schema(reader)
        _require_schema(writer)
        start = len(self.changes)
        if canon(reader_extra) != canon(writer_extra):
            self._emit(
                f"{path}/$ref",
                "unsupported_keyword",
                Severity.UNKNOWN,
                "keywords next to $ref differ and are not analysed",
            )
        if isinstance(reader, bool) and isinstance(writer, bool):
            if reader != writer:
                severity = Severity.COMPATIBLE if reader else Severity.BREAKING
                self._emit_schema_change(path, bool_kind, reader, writer, severity)
            return _worst(self.changes[start:])
        if isinstance(reader, bool) and not reader:
            self._emit_schema_change(path, bool_kind, reader, writer, Severity.BREAKING)
            return _worst(self.changes[start:])
        if isinstance(writer, bool) and not writer:
            self._emit_schema_change(path, bool_kind, reader, writer, Severity.COMPATIBLE)
            return _worst(self.changes[start:])
        if isinstance(reader, bool):
            reader = {}
        if isinstance(writer, bool):
            writer = {}
        key = (rptr, wptr, self.quiet)
        so_far = _worst(self.changes[start:])
        if key in self.memo:
            return _higher(so_far, self.memo[key])
        if key in self.stack:
            return so_far
        if len(self.memo) + len(self.stack) >= _MAX_PAIRS:
            raise SchemaCompatError(
                "too_complex", f"more than {_MAX_PAIRS} schema pairs to compare"
            )
        inner = len(self.changes)
        self.stack.add(key)
        try:
            self._compare_dicts(reader, writer, path, rptr, wptr, depth)
        finally:
            self.stack.discard(key)
        result = _worst(self.changes[inner:])
        self.memo[key] = result
        return _higher(so_far, result)

    def _compare_dicts(
        self,
        reader: dict[str, Any],
        writer: dict[str, Any],
        path: str,
        rptr: str,
        wptr: str,
        depth: int,
    ) -> None:
        self._compare_types(reader, writer, path)
        self._compare_values(reader, writer, path)
        self._compare_bounds(reader, writer, path)
        self._compare_object(reader, writer, path, rptr, wptr, depth)
        self._compare_items(reader, writer, path, rptr, wptr, depth)
        self._compare_unsupported(reader, writer, path)

    def _compare_types(self, reader: dict[str, Any], writer: dict[str, Any], path: str) -> None:
        reader_types, writer_types = _type_set(reader), _type_set(writer)
        reader_all, writer_all = _expand(reader_types), _expand(writer_types)
        if reader_all == writer_all:
            return
        severity = Severity.COMPATIBLE if writer_all <= reader_all else Severity.BREAKING
        old, new = self._old_new(reader_types, writer_types)
        detail = f"type changed from {_fmt_type(old)} to {_fmt_type(new)}"
        self._emit(f"{path}/type", "type_changed", severity, detail)

    def _compare_values(self, reader: dict[str, Any], writer: dict[str, Any], path: str) -> None:
        reader_values, writer_values = _allowed(reader), _allowed(writer)
        if reader_values is None and writer_values is None:
            return
        if (
            reader_values is not None
            and writer_values is not None
            and reader_values.keys() == writer_values.keys()
        ):
            return
        if reader_values is None:
            severity = Severity.COMPATIBLE
        elif writer_values is None:
            severity = Severity.BREAKING
        elif writer_values.keys() <= reader_values.keys():
            severity = Severity.COMPATIBLE
        else:
            severity = Severity.BREAKING
        old, new = self._old_new(reader_values, writer_values)
        keyword = "const" if "const" in reader or "const" in writer else "enum"
        kind = "schema_changed" if keyword == "const" else "enum_changed"
        detail = f"allowed values changed from {_show(old)} to {_show(new)}"
        self._emit(f"{path}/{keyword}", kind, severity, detail)

    def _compare_bounds(self, reader: dict[str, Any], writer: dict[str, Any], path: str) -> None:
        for inclusive, exclusive, lower, integer in _BOUNDS:
            reader_bound = _bound(reader, inclusive, exclusive, lower, integer)
            writer_bound = _bound(writer, inclusive, exclusive, lower, integer)
            reader_key = _bound_key(reader_bound, lower)
            writer_key = _bound_key(writer_bound, lower)
            if reader_key == writer_key:
                continue
            stricter = reader_key is not None and (writer_key is None or reader_key > writer_key)
            severity = Severity.BREAKING if stricter else Severity.COMPATIBLE
            old, new = self._old_new(reader_bound, writer_bound)
            source = new if new is not None else old
            detail = f"constraint changed from {_bound_text(old)} to {_bound_text(new)}"
            self._emit(f"{path}/{source[2]}", "constraint_changed", severity, detail)

    def _compare_object(
        self,
        reader: dict[str, Any],
        writer: dict[str, Any],
        path: str,
        rptr: str,
        wptr: str,
        depth: int,
    ) -> None:
        props_r, props_w = _properties(reader), _properties(writer)
        extra_r, extra_w = _additional(reader), _additional(writer)
        extra_rptr = f"{rptr}/additionalProperties"
        extra_wptr = f"{wptr}/additionalProperties"
        for name in sorted(props_r.keys() | props_w.keys()):
            escaped = _esc(name)
            child = f"{path}/properties/{escaped}"
            child_r = f"{rptr}/properties/{escaped}"
            child_w = f"{wptr}/properties/{escaped}"
            if name in props_r and name in props_w:
                self.compare(props_r[name], props_w[name], child, child_r, child_w, depth + 1)
            elif name in props_r:
                severity = Severity.COMPATIBLE
                if isinstance(extra_w, dict):
                    severity = self._summarize(
                        props_r[name], extra_w, child, child_r, extra_wptr, depth + 1
                    )
                self._emit_property(child, name, not self.swap, severity)
            else:
                if extra_r is False:
                    severity = Severity.BREAKING
                elif isinstance(extra_r, dict):
                    severity = self._summarize(
                        extra_r, props_w[name], child, extra_rptr, child_w, depth + 1
                    )
                else:
                    severity = Severity.COMPATIBLE
                self._emit_property(child, name, self.swap, severity)
        required_r, required_w = _required(reader), _required(writer)
        for name in sorted(required_r - required_w):
            self._emit_required(path, name, not self.swap, Severity.BREAKING)
        for name in sorted(required_w - required_r):
            self._emit_required(path, name, self.swap, Severity.COMPATIBLE)
        self.compare(
            extra_r,
            extra_w,
            f"{path}/additionalProperties",
            extra_rptr,
            extra_wptr,
            depth + 1,
            "additional_properties_changed",
        )

    def _compare_items(
        self,
        reader: dict[str, Any],
        writer: dict[str, Any],
        path: str,
        rptr: str,
        wptr: str,
        depth: int,
    ) -> None:
        if "items" not in reader and "items" not in writer:
            return
        items_r, items_w = reader.get("items", True), writer.get("items", True)
        if isinstance(items_r, list) or isinstance(items_w, list):
            if canon(items_r) != canon(items_w):
                self._emit(
                    f"{path}/items",
                    "unsupported_keyword",
                    Severity.UNKNOWN,
                    "tuple-form items differ and are not analysed",
                )
            return
        self.compare(items_r, items_w, f"{path}/items", f"{rptr}/items", f"{wptr}/items", depth + 1)

    def _inline(self, node: Any, root: Any, seen: tuple[str, ...]) -> Any:
        """Replace local ``$ref`` objects by their targets; cycles become a marker."""
        if isinstance(node, list):
            return [self._inline(item, root, seen) for item in node]
        if not isinstance(node, dict):
            return node
        ref = node.get("$ref")
        if isinstance(ref, str):
            if ref in seen:
                return {"$cycle": ref}
            target, _ = _resolve_ref(ref, root)
            rest = {k: self._inline(v, root, seen) for k, v in node.items() if k != "$ref"}
            return {"$ref": self._inline(target, root, (*seen, ref)), **rest}
        return {k: self._inline(v, root, seen) for k, v in node.items()}

    def _compare_unsupported(
        self, reader: dict[str, Any], writer: dict[str, Any], path: str
    ) -> None:
        for key in sorted(reader.keys() | writer.keys()):
            if key in _SUPPORTED or key in _ANNOTATIONS:
                continue
            if (
                key in reader
                and key in writer
                and canon(reader[key]) == canon(writer[key])
                and canon(self._inline(reader[key], self.reader_root, ()))
                == canon(self._inline(writer[key], self.writer_root, ()))
            ):
                continue
            self._emit(
                f"{path}/{_esc(key)}",
                "unsupported_keyword",
                Severity.UNKNOWN,
                f"keyword {_q(key)} differs and is not analysed",
            )


def _run(reader: Any, writer: Any, swap: bool, direction: Direction) -> list[Change]:
    walker = _Walker(reader, writer, swap)
    walker.compare(reader, writer, "", "", "", 0)
    return [
        replace(change, direction=direction) if change.severity is Severity.BREAKING else change
        for change in walker.changes
    ]


def _by_key(changes: list[Change]) -> dict[tuple[str, str, str], Change]:
    result: dict[tuple[str, str, str], Change] = {}
    for change in changes:
        key = (change.path, change.kind, change.detail)
        existing = result.get(key)
        if existing is None or _RANK[change.severity] > _RANK[existing.severity]:
            result[key] = change
    return result


def _merge(backward: list[Change], forward: list[Change]) -> list[Change]:
    by_backward, by_forward = _by_key(backward), _by_key(forward)
    merged: list[Change] = []
    for key in by_backward.keys() | by_forward.keys():
        first, second = by_backward.get(key), by_forward.get(key)
        if (
            first is not None
            and second is not None
            and first.severity is Severity.BREAKING
            and second.severity is Severity.BREAKING
        ):
            merged.append(replace(first, direction="both"))
            continue
        candidates = [item for item in (first, second) if item is not None]
        merged.append(max(candidates, key=lambda item: _RANK[item.severity]))
    return merged


def diff(
    old: dict[str, Any] | bool,
    new: dict[str, Any] | bool,
    mode: Mode = Mode.BACKWARD,
) -> list[Change]:
    """Compare two JSON Schemas and classify every difference.

    A change is breaking for a direction when some instance valid under the writer schema
    is invalid under the reader schema. BACKWARD: reader is ``new``, writer is ``old``.
    FORWARD: reader is ``old``, writer is ``new``. FULL reports both and marks the direction
    that breaks. The result is sorted by ``(path, kind, detail)``.

    Raises:
        SchemaCompatError: for invalid schemas, unsupported references, nesting deeper than
            64 levels or comparisons that exceed the internal limits.
        TypeError: when ``mode`` is not a :class:`Mode`.
    """
    if not isinstance(mode, Mode):
        raise TypeError("mode must be a Mode")
    for schema in (old, new):
        scan_value(schema, DEFAULT_MAX_DEPTH)
        _require_schema(schema)
    try:
        if mode is Mode.BACKWARD:
            changes = _run(new, old, False, "backward")
        elif mode is Mode.FORWARD:
            changes = _run(old, new, True, "forward")
        else:
            changes = _merge(_run(new, old, False, "backward"), _run(old, new, True, "forward"))
    except RecursionError:
        raise SchemaCompatError(
            "too_deep", "schema nesting exhausted the recursion limit"
        ) from None
    changes.sort(key=lambda change: (change.path, change.kind, change.detail))
    logger.debug("compared schemas in %s mode: %d change(s)", mode.value, len(changes))
    return changes
