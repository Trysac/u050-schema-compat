"""Behavioural tests for ``schema_compat.diff``."""

from __future__ import annotations

from typing import Any

import pytest

from schema_compat import Change, Mode, SchemaCompatError, Severity, diff, engine

COMPAT = Severity.COMPATIBLE
BREAKING = Severity.BREAKING
UNKNOWN = Severity.UNKNOWN

OLD: dict[str, Any] = {
    "type": "object",
    "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
    "required": ["id", "name"],
}
NEW: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "email": {"type": "string", "default": "x"},
    },
    "required": ["id", "name", "email"],
}


def _code(old: Any, new: Any) -> str:
    with pytest.raises(SchemaCompatError) as info:
        diff(old, new)
    return info.value.code


def test_required_added_is_breaking_backward() -> None:
    changes = diff(OLD, NEW, Mode.BACKWARD)
    expected = Change(
        path="/required",
        kind="required_added",
        severity=Severity.BREAKING,
        direction="backward",
    )
    assert expected in changes
    assert Change("/properties/email", "property_added", COMPAT, None) in changes
    assert len(changes) == 2
    required = [change for change in changes if change.kind == "required_added"]
    assert "email" in required[0].detail


def test_dropping_required_property_per_mode() -> None:
    dropped = {**OLD, "required": ["id"]}
    backward = Change("/required", "required_removed", COMPAT, None)
    forward = Change("/required", "required_removed", BREAKING, "forward")
    assert diff(OLD, dropped, Mode.BACKWARD) == [backward]
    assert diff(OLD, dropped, Mode.FORWARD) == [forward]


def test_full_mode_merges_directions() -> None:
    changes = diff(OLD, NEW, Mode.FULL)
    assert Change("/required", "required_added", BREAKING, "backward") in changes
    assert Change("/properties/email", "property_added", COMPAT, None) in changes
    both = diff({"type": "string"}, {"type": "integer"}, Mode.FULL)
    assert both == [Change("/type", "type_changed", BREAKING, "both")]
    widened = diff({"type": "integer"}, {"type": "number"}, Mode.FULL)
    assert widened == [Change("/type", "type_changed", BREAKING, "forward")]
    unknown = diff({}, {"if": {}}, Mode.FULL)
    assert unknown == [Change("/if", "unsupported_keyword", UNKNOWN, None)]


def test_integer_to_number() -> None:
    old, new = {"type": "integer"}, {"type": "number"}
    assert diff(old, new, Mode.BACKWARD) == [Change("/type", "type_changed", COMPAT, None)]
    assert diff(old, new, Mode.FORWARD) == [Change("/type", "type_changed", BREAKING, "forward")]
    assert diff(new, old, Mode.BACKWARD) == [Change("/type", "type_changed", BREAKING, "backward")]


def test_incompatible_types_and_unions() -> None:
    old, new = {"type": "string"}, {"type": "integer"}
    assert diff(old, new, Mode.BACKWARD) == [Change("/type", "type_changed", BREAKING, "backward")]
    assert diff(old, new, Mode.FORWARD) == [Change("/type", "type_changed", BREAKING, "forward")]
    union, single = {"type": ["string", "null"]}, {"type": "string"}
    assert diff(union, single, Mode.BACKWARD) == [
        Change("/type", "type_changed", BREAKING, "backward")
    ]
    assert diff(union, single, Mode.FORWARD) == [Change("/type", "type_changed", COMPAT, None)]
    assert diff({"type": ["null", "string"]}, union) == []
    assert diff({"type": "number"}, {"type": ["number", "integer"]}) == []


def test_missing_type_means_any_type() -> None:
    assert diff({}, {"type": "string"}, Mode.BACKWARD)[0].severity is BREAKING
    assert diff({}, {"type": "string"}, Mode.FORWARD)[0].severity is COMPAT


def test_optional_property_added() -> None:
    old = {"type": "object", "properties": {"id": {"type": "string"}}}
    new = {"type": "object", "properties": {"id": {"type": "string"}, "nick": {"type": "string"}}}
    added = Change("/properties/nick", "property_added", COMPAT, None)
    assert diff(old, new, Mode.BACKWARD) == [added]
    assert diff(old, new, Mode.FORWARD) == [added]
    closed_old = {**old, "additionalProperties": False}
    closed_new = {**new, "additionalProperties": False}
    breaking = Change("/properties/nick", "property_added", BREAKING, "forward")
    assert diff(closed_old, closed_new, Mode.FORWARD) == [breaking]
    assert diff(closed_old, closed_new, Mode.BACKWARD) == [added]


def test_removed_property_breaks_a_closed_reader() -> None:
    old = {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "string"}}}
    only_a = {"type": "object", "properties": {"a": {"type": "string"}}}
    closed = {**only_a, "additionalProperties": False}
    removed = Change("/properties/b", "property_removed", BREAKING, "backward")
    assert removed in diff(old, closed, Mode.BACKWARD)
    assert diff(old, only_a, Mode.BACKWARD) == [
        Change("/properties/b", "property_removed", COMPAT, None)
    ]
    assert diff(old, only_a, Mode.FORWARD) == [
        Change("/properties/b", "property_removed", COMPAT, None)
    ]


def test_added_property_is_checked_against_additional_properties_schema() -> None:
    old = {"type": "object", "additionalProperties": {"type": "string"}}
    fits = {**old, "properties": {"p": {"type": "string"}}}
    clashes = {**old, "properties": {"p": {"type": "integer"}}}
    assert diff(old, fits, Mode.BACKWARD) == [
        Change("/properties/p", "property_added", COMPAT, None)
    ]
    assert diff(old, clashes, Mode.BACKWARD) == [
        Change("/properties/p", "property_added", BREAKING, "backward")
    ]
    assert diff(old, fits, Mode.FORWARD) == [
        Change("/properties/p", "property_added", COMPAT, None)
    ]
    assert diff(old, clashes, Mode.FORWARD) == [
        Change("/properties/p", "property_added", BREAKING, "forward")
    ]


TIGHTENING: list[tuple[dict[str, Any], dict[str, Any], str, str]] = [
    ({"enum": [1, 2, 3]}, {"enum": [1, 2]}, "/enum", "enum_changed"),
    ({}, {"enum": [1]}, "/enum", "enum_changed"),
    ({"maxLength": 10}, {"maxLength": 5}, "/maxLength", "constraint_changed"),
    ({}, {"maxLength": 5}, "/maxLength", "constraint_changed"),
    ({"minimum": 0}, {"minimum": 1}, "/minimum", "constraint_changed"),
    ({"maximum": 10}, {"maximum": 5}, "/maximum", "constraint_changed"),
    ({"exclusiveMinimum": 0}, {"exclusiveMinimum": 1}, "/exclusiveMinimum", "constraint_changed"),
    ({"exclusiveMaximum": 10}, {"exclusiveMaximum": 5}, "/exclusiveMaximum", "constraint_changed"),
    ({"minLength": 1}, {"minLength": 3}, "/minLength", "constraint_changed"),
    ({"minItems": 0}, {"minItems": 2}, "/minItems", "constraint_changed"),
    ({"maxItems": 9}, {"maxItems": 3}, "/maxItems", "constraint_changed"),
]


@pytest.mark.parametrize(("old", "new", "path", "kind"), TIGHTENING)
def test_tightening_is_breaking_backward_and_swaps(
    old: dict[str, Any], new: dict[str, Any], path: str, kind: str
) -> None:
    breaking_backward = Change(path, kind, BREAKING, "backward")
    breaking_forward = Change(path, kind, BREAKING, "forward")
    compatible = Change(path, kind, COMPAT, None)
    assert diff(old, new, Mode.BACKWARD) == [breaking_backward]
    assert diff(old, new, Mode.FORWARD) == [compatible]
    assert diff(new, old, Mode.BACKWARD) == [compatible]
    assert diff(new, old, Mode.FORWARD) == [breaking_forward]


def test_enum_uses_json_equality() -> None:
    for mode in (Mode.BACKWARD, Mode.FORWARD, Mode.FULL):
        assert diff({"enum": [1]}, {"enum": [1.0]}, mode) == []
        assert diff({"enum": [[1, 2], {"a": 1}]}, {"enum": [[1.0, 2], {"a": 1.0}]}, mode) == []
        assert diff({"enum": [None]}, {"enum": [None]}, mode) == []
    assert diff({"enum": [1]}, {"enum": [True]}, Mode.BACKWARD) == [
        Change("/enum", "enum_changed", BREAKING, "backward")
    ]
    assert diff({"enum": [1]}, {"enum": [True]}, Mode.FORWARD) == [
        Change("/enum", "enum_changed", BREAKING, "forward")
    ]
    assert diff({"enum": [1]}, {"enum": [True]}, Mode.FULL) == [
        Change("/enum", "enum_changed", BREAKING, "both")
    ]
    assert diff({"enum": [0]}, {"enum": [False]}, Mode.FULL)[0].direction == "both"
    assert diff({"enum": [[1, 2]]}, {"enum": [[2, 1]]}, Mode.FULL)[0].direction == "both"
    assert diff({"enum": [None]}, {"enum": [0]}, Mode.FULL)[0].direction == "both"
    assert diff({"enum": ["a"]}, {"enum": ["a", "a"]}) == []


def test_const_changes() -> None:
    assert diff({"const": 1}, {"const": 2}, Mode.FULL) == [
        Change("/const", "schema_changed", BREAKING, "both")
    ]
    assert diff({"const": 1}, {"enum": [1, 2]}, Mode.BACKWARD) == [
        Change("/const", "schema_changed", COMPAT, None)
    ]
    assert diff({"const": 1, "enum": [2]}, {"enum": [2]}, Mode.BACKWARD)[0].severity is COMPAT
    assert diff({"const": 1.0}, {"const": 1}) == []


def test_large_enum_detail_is_bounded() -> None:
    old = {"enum": [f"value-{index}" for index in range(200)]}
    new = {"enum": [f"other-{index}" for index in range(200)]}
    changes = diff(old, new, Mode.FULL)
    assert all(len(change.detail) <= 200 for change in changes)


def test_annotations_never_affect_compatibility() -> None:
    old = {
        "type": "object",
        "properties": {"a": {"type": "string", "default": "x", "title": "A"}},
        "title": "T",
        "description": "d",
        "examples": [{"a": "x"}],
        "default": {},
    }
    new = {
        "type": "object",
        "properties": {"a": {"type": "string", "default": "y", "description": "changed"}},
        "title": "Other",
        "examples": [],
        "$comment": "note",
        "$schema": "https://json-schema.org/draft/2020-12/schema",
    }
    for mode in (Mode.BACKWARD, Mode.FORWARD, Mode.FULL):
        assert diff(old, new, mode) == []


def test_moving_a_schema_into_defs_behind_a_ref_changes_nothing() -> None:
    old = {"type": "object", "properties": {"a": {"type": "string", "minLength": 1}}}
    new = {
        "type": "object",
        "properties": {"a": {"$ref": "#/$defs/a"}},
        "$defs": {"a": {"type": "string", "minLength": 1}},
    }
    for mode in (Mode.BACKWARD, Mode.FORWARD, Mode.FULL):
        assert diff(old, new, mode) == []
        assert diff(new, old, mode) == []


@pytest.mark.parametrize(
    ("ref", "container", "key"),
    [
        ("#/$defs/a~1b", "$defs", "a/b"),
        ("#/$defs/a~0b", "$defs", "a~b"),
        ("#/$defs/a%20b", "$defs", "a b"),
        ("#/definitions/x", "definitions", "x"),
    ],
)
def test_ref_pointers_resolve(ref: str, container: str, key: str) -> None:
    def build(kind: str) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"x": {"$ref": ref}},
            container: {key: {"type": kind}},
        }

    changes = diff(build("string"), build("integer"), Mode.BACKWARD)
    assert [(change.path, change.kind) for change in changes] == [
        ("/properties/x/type", "type_changed")
    ]


def _ref_schema(ref: str, defs: dict[str, Any]) -> dict[str, Any]:
    return {"properties": {"a": {"$ref": ref}}, "$defs": defs}


def test_ref_into_array_index_and_root() -> None:
    defs = {"list": [{"type": "string"}]}
    assert diff(_ref_schema("#/$defs/list/0", defs), _ref_schema("#/$defs/list/0", defs)) == []
    assert _code({"$ref": "#"}, {"$ref": "#"}) == "invalid_schema"


def test_recursive_tree_schema_terminates() -> None:
    def tree(value_type: str) -> dict[str, Any]:
        return {
            "$ref": "#/$defs/node",
            "$defs": {
                "node": {
                    "type": "object",
                    "properties": {
                        "value": {"type": value_type},
                        "children": {"type": "array", "items": {"$ref": "#/$defs/node"}},
                    },
                    "required": ["value"],
                }
            },
        }

    assert diff(tree("integer"), tree("integer"), Mode.FULL) == []
    changes = diff(tree("integer"), tree("string"), Mode.BACKWARD)
    assert [(change.path, change.kind) for change in changes] == [
        ("/properties/value/type", "type_changed")
    ]


def test_shared_definition_is_reported_once() -> None:
    def build(kind: str) -> dict[str, Any]:
        return {
            "properties": {"a": {"$ref": "#/$defs/x"}, "b": {"$ref": "#/$defs/x"}},
            "$defs": {"x": {"type": kind}},
        }

    changes = diff(build("string"), build("integer"), Mode.BACKWARD)
    assert [(change.path, change.kind) for change in changes] == [
        ("/properties/a/type", "type_changed")
    ]


@pytest.mark.parametrize(
    "ref", ["other.json#/x", "#node", "http://example.com/s.json#/a", "definitions.json"]
)
def test_unsupported_refs(ref: str) -> None:
    schema = _ref_schema(ref, {})
    assert _code(schema, schema) == "unsupported_ref"


@pytest.mark.parametrize(
    "ref",
    [
        "#/$defs/missing",
        "#/$defs/list/5",
        "#/$defs/list/x",
        "#/$defs/list/00",
        "#/$defs/s/b",
        "#/$defs/%FF",
    ],
)
def test_unresolvable_refs_are_invalid_schemas(ref: str) -> None:
    schema = _ref_schema(ref, {"list": [{}], "s": "text"})
    assert _code(schema, schema) == "invalid_schema"


def test_ref_cycles_and_oversized_messages() -> None:
    assert _code({"$ref": "#"}, {}) == "invalid_schema"
    with pytest.raises(SchemaCompatError) as info:
        long_ref = _ref_schema("#/" + "x" * 1000, {})
        diff(long_ref, long_ref)
    assert len(info.value.message) <= 200
    assert _code({}, {"$ref": 5}) == "invalid_schema"


def test_keywords_next_to_a_ref_are_compared_for_equality() -> None:
    def build(min_length: int) -> dict[str, Any]:
        target = {"s": {"type": "string"}}
        return {
            "properties": {"a": {"$ref": "#/$defs/s", "minLength": min_length}},
            "$defs": target,
        }

    assert diff(build(1), build(2)) == [
        Change("/properties/a/$ref", "unsupported_keyword", UNKNOWN, None)
    ]
    assert diff(build(1), build(1)) == []


@pytest.mark.parametrize(
    "keyword", ["if", "then", "else", "patternProperties", "dependentSchemas", "prefixItems"]
)
def test_unsupported_keywords_are_unknown(keyword: str) -> None:
    expected = [Change(f"/{keyword}", "unsupported_keyword", UNKNOWN, None)]
    assert diff({"type": "array"}, {"type": "array", keyword: {}}, Mode.BACKWARD) == expected
    assert diff({"type": "array"}, {"type": "array", keyword: {}}, Mode.FORWARD) == expected


@pytest.mark.parametrize("keyword", ["oneOf", "anyOf"])
def test_one_of_and_any_of(keyword: str) -> None:
    first = {keyword: [{"type": "string"}]}
    second = {keyword: [{"type": "integer"}]}
    assert diff(first, first, Mode.FULL) == []
    assert diff(first, second, Mode.BACKWARD) == [
        Change(f"/{keyword}", "unsupported_keyword", UNKNOWN, None)
    ]


def test_unsupported_keyword_name_is_escaped_and_bounded() -> None:
    name = "k/" + "k" * 500
    changes = diff({}, {name: 1})
    assert changes[0].path.startswith("/k~1kkk")
    assert len(changes[0].detail) < 200


def test_boolean_schemas() -> None:
    for mode in (Mode.BACKWARD, Mode.FORWARD, Mode.FULL):
        assert diff(True, {}, mode) == []
        assert diff({}, True, mode) == []
        assert diff(True, True, mode) == []
        assert diff(False, False, mode) == []
    assert diff({"type": "string"}, False, Mode.BACKWARD) == [
        Change("", "schema_changed", BREAKING, "backward")
    ]
    assert diff({"type": "string"}, False, Mode.FORWARD) == [
        Change("", "schema_changed", COMPAT, None)
    ]
    assert diff(False, True, Mode.BACKWARD) == [Change("", "schema_changed", COMPAT, None)]
    assert diff(False, True, Mode.FORWARD) == [Change("", "schema_changed", BREAKING, "forward")]
    old = {"properties": {"a": True}}
    new = {"properties": {"a": {"type": "string"}}}
    assert diff(old, new, Mode.BACKWARD) == [
        Change("/properties/a/type", "type_changed", BREAKING, "backward")
    ]


def test_additional_properties_changes() -> None:
    closed = {"type": "object", "additionalProperties": False}
    open_schema = {"type": "object"}
    path = "/additionalProperties"
    kind = "additional_properties_changed"
    assert diff(closed, open_schema, Mode.BACKWARD) == [Change(path, kind, COMPAT, None)]
    assert diff(closed, open_schema, Mode.FORWARD) == [Change(path, kind, BREAKING, "forward")]
    typed = {"type": "object", "additionalProperties": {"type": "string"}}
    assert diff(typed, closed, Mode.BACKWARD) == [Change(path, kind, BREAKING, "backward")]
    assert diff(typed, closed, Mode.FORWARD) == [Change(path, kind, COMPAT, None)]
    other = {"type": "object", "additionalProperties": {"type": "integer"}}
    assert diff(typed, other, Mode.FULL) == [
        Change("/additionalProperties/type", "type_changed", BREAKING, "both")
    ]
    assert diff(open_schema, {**open_schema, "additionalProperties": True}) == []


def test_items() -> None:
    old = {"type": "array", "items": {"type": "string"}}
    new = {"type": "array", "items": {"type": "integer"}}
    assert diff(old, new, Mode.FULL) == [Change("/items/type", "type_changed", BREAKING, "both")]
    assert diff({"type": "array"}, old, Mode.BACKWARD)[0].path == "/items/type"
    tuple_form = {"items": [{"type": "string"}]}
    assert diff(tuple_form, tuple_form) == []
    assert diff(tuple_form, {"items": [{"type": "integer"}]}) == [
        Change("/items", "unsupported_keyword", UNKNOWN, None)
    ]
    objects = {"type": "array", "items": {"type": "object", "required": ["id"]}}
    assert diff(objects, {"type": "array", "items": {"type": "object"}}) == [
        Change("/items/required", "required_removed", COMPAT, None)
    ]


def test_bounds_combine_inclusive_and_exclusive_forms() -> None:
    assert diff({"minimum": 1}, {"exclusiveMinimum": 0}, Mode.BACKWARD) == [
        Change("/exclusiveMinimum", "constraint_changed", COMPAT, None)
    ]
    assert diff({"minimum": 0}, {"exclusiveMinimum": 0}, Mode.BACKWARD) == [
        Change("/exclusiveMinimum", "constraint_changed", BREAKING, "backward")
    ]
    assert diff({"minimum": 0, "exclusiveMinimum": 0}, {"exclusiveMinimum": 0}) == []
    assert diff({"minimum": 5, "exclusiveMinimum": 1}, {"minimum": 5}) == []
    assert diff({"minimum": 0}, {"minimum": 0.0}) == []
    assert diff({"minLength": 2.0}, {"minLength": 2}) == []


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "nope"},
        {"type": []},
        {"type": [1]},
        {"type": 5},
        {"enum": 3},
        {"required": "id"},
        {"required": [1]},
        {"properties": []},
        {"properties": {"a": 3}},
        {"additionalProperties": 3},
        {"items": 5},
        {"minLength": -1},
        {"minLength": 1.5},
        {"minimum": "0"},
        {"exclusiveMinimum": True},
        {"exclusiveMaximum": False},
        {"maxItems": True},
    ],
)
def test_invalid_schemas_are_rejected(bad: dict[str, Any]) -> None:
    assert _code({"properties": {"a": {}}}, bad) == "invalid_schema"


def test_invalid_inputs() -> None:
    assert _code([], {}) == "invalid_schema"
    assert _code("x", {}) == "invalid_schema"
    assert _code({1: 2}, {}) == "invalid_schema"
    assert _code({"minimum": float("nan")}, {}) == "invalid_schema"
    assert _code({"default": object()}, {}) == "invalid_schema"
    with pytest.raises(TypeError):
        diff({}, {}, "backward")  # type: ignore[arg-type]


def test_in_memory_depth_limit() -> None:
    schema: dict[str, Any] = {}
    node = schema
    for _ in range(65):
        node["a"] = {}
        node = node["a"]
    assert _code(schema, {}) == "too_deep"


def _chain(levels: int) -> dict[str, Any]:
    return {"properties": {"a": _chain(levels - 1)}} if levels else {}


def test_internal_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    many = {"properties": {f"p{index}": {} for index in range(10)}}
    with monkeypatch.context() as patch:
        patch.setattr(engine, "_MAX_PAIRS", 5)
        assert _code(many, many) == "too_complex"
    with monkeypatch.context() as patch:
        patch.setattr(engine, "_MAX_CHANGES", 1)
        assert _code({}, {"if": {}, "then": {}}) == "too_complex"
    with monkeypatch.context() as patch:
        patch.setattr(engine, "_MAX_WALK_DEPTH", 3)
        assert _code(_chain(6), _chain(6)) == "too_deep"


def test_recursion_error_maps_to_too_deep(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: Any, **kwargs: Any) -> None:
        raise RecursionError

    monkeypatch.setattr(engine, "_run", boom)
    assert _code({}, {}) == "too_deep"


def test_result_is_sorted_and_deterministic() -> None:
    changes = diff(OLD, NEW, Mode.FULL)
    assert changes == sorted(changes, key=lambda change: (change.path, change.kind, change.detail))
    assert changes == diff(OLD, NEW, Mode.FULL)


def test_detail_is_not_part_of_equality() -> None:
    first = Change("/a", "type_changed", COMPAT, None, "one")
    second = Change("/a", "type_changed", COMPAT, None, "two")
    assert first == second
    assert hash(first) == hash(second)
