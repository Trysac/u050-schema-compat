"""Tests for ``schema_compat.load_schema`` and the error type."""

from __future__ import annotations

from pathlib import Path

import pytest

from schema_compat import SchemaCompatError, load_schema


def _nested_object(depth: int) -> str:
    return '{"a":' * (depth - 1) + "{}" + "}" * (depth - 1)


def _code(path: Path, **limits: int) -> str:
    with pytest.raises(SchemaCompatError) as info:
        load_schema(path, **limits)
    return info.value.code


def test_reads_objects_and_booleans(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    path.write_text('{"type": "string"}', encoding="utf-8")
    assert load_schema(path) == {"type": "string"}
    path.write_text("true", encoding="utf-8")
    assert load_schema(path) is True
    path.write_bytes(b"\xef\xbb\xbf{}")
    assert load_schema(path) == {}


def test_size_limit_is_exact(tmp_path: Path) -> None:
    max_bytes = 64
    exact = tmp_path / "exact.json"
    exact.write_bytes(b"{}".ljust(max_bytes))
    assert load_schema(exact, max_bytes=max_bytes) == {}
    over = tmp_path / "over.json"
    over.write_bytes(b"{}".ljust(max_bytes + 1))
    assert _code(over, max_bytes=max_bytes) == "input_too_large"


def test_depth_limit_is_exact(tmp_path: Path) -> None:
    path = tmp_path / "deep.json"
    path.write_text(_nested_object(64), encoding="utf-8")
    assert isinstance(load_schema(path, max_depth=64), dict)
    path.write_text(_nested_object(65), encoding="utf-8")
    assert _code(path, max_depth=64) == "too_deep"
    path.write_text("[" * 65 + "]" * 65, encoding="utf-8")
    assert _code(path, max_depth=64) == "too_deep"


def test_hostile_nesting_maps_to_too_deep(tmp_path: Path) -> None:
    path = tmp_path / "hostile.json"
    path.write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")
    assert _code(path) == "too_deep"


@pytest.mark.parametrize(
    "content",
    [
        b"{",
        b"",
        b"{'a': 1}",
        b'{"minimum": NaN}',
        b'{"minimum": Infinity}',
        b'{"minimum": 1e999}',
        b"\xff\xfe",
    ],
)
def test_invalid_json(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "bad.json"
    path.write_bytes(content)
    assert _code(path) == "invalid_json"


@pytest.mark.parametrize("content", ["[]", "5", '"text"', "null"])
def test_top_level_must_be_a_schema(tmp_path: Path, content: str) -> None:
    path = tmp_path / "top.json"
    path.write_text(content, encoding="utf-8")
    assert _code(path) == "invalid_schema"


def test_argument_and_file_errors(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        load_schema(path, max_bytes=-1)
    with pytest.raises(ValueError):
        load_schema(path, max_depth=0)
    with pytest.raises(OSError):
        load_schema(tmp_path / "missing.json")


def test_error_type_is_bounded() -> None:
    error = SchemaCompatError("too_deep", "x" * 500)
    assert error.code == "too_deep"
    assert len(error.message) == 200
    assert str(error) == error.message
    assert isinstance(error, Exception)
