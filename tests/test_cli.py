"""Tests for rendering, verdicts and the command line interface."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest

from schema_compat import Change, Severity, is_compatible, render
from schema_compat import __main__ as entry
from schema_compat.__main__ import main

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


def _write(tmp_path: Path, name: str, data: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_is_compatible() -> None:
    compatible = Change("/a", "type_changed", Severity.COMPATIBLE, None)
    unknown = Change("/b", "unsupported_keyword", Severity.UNKNOWN, None)
    breaking = Change("/c", "required_added", Severity.BREAKING, "backward")
    assert is_compatible([])
    assert is_compatible([compatible, unknown])
    assert not is_compatible([compatible, unknown], strict=True)
    assert not is_compatible([breaking])
    assert is_compatible([compatible], strict=True)


def test_render_text_and_json() -> None:
    change = Change("/a", "type_changed", Severity.BREAKING, "backward", "details")
    root = Change("", "schema_changed", Severity.COMPATIBLE, None, "root")
    assert render([change], "text") == "BREAKING /a type_changed: details"
    assert render([root], "text") == "COMPATIBLE (root) schema_changed: root"
    assert render([], "text") == ""
    assert render([], "json") == "[]"
    rows = json.loads(render([change, root], "json"))
    assert [row["path"] for row in rows] == ["", "/a"]
    assert list(rows[1]) == ["path", "kind", "severity", "direction", "detail"]
    assert rows[0]["direction"] is None
    with pytest.raises(ValueError):
        render([change], "yaml")  # type: ignore[arg-type]


def test_compatible_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    old = _write(tmp_path, "old.json", OLD)
    assert main([str(old), str(old)]) == 0
    assert capsys.readouterr().out == ""


def test_breaking_exits_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    old = _write(tmp_path, "old.json", OLD)
    new = _write(tmp_path, "new.json", NEW)
    assert main([str(old), str(new)]) == 1
    out = capsys.readouterr().out
    assert 'BREAKING /required required_added: property "email" is now required' in out
    assert main([str(old), str(new), "--mode", "forward"]) == 0
    assert "COMPATIBLE" in capsys.readouterr().out
    assert main([str(old), str(new), "--mode", "full"]) == 1


def test_json_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def schema(min_length: int, extra: dict[str, Any]) -> dict[str, Any]:
        email = {"type": "string", "minLength": min_length}
        user = {"type": "object", "properties": {"email": email}}
        return {"type": "object", "properties": {"user": user}, **extra}

    old = _write(tmp_path, "old.json", schema(1, {}))
    new = _write(tmp_path, "new.json", schema(5, {"if": {}}))
    assert main([str(old), str(new), "--format", "json"]) == 1
    rows = json.loads(capsys.readouterr().out)
    assert isinstance(rows, list)
    assert all(list(row) == ["path", "kind", "severity", "direction", "detail"] for row in rows)
    assert rows == sorted(rows, key=lambda row: (row["path"], row["kind"]))
    paths = [row["path"] for row in rows]
    assert "/properties/user/properties/email/minLength" in paths
    assert "/if" in paths


def test_strict_fails_on_unknown(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    old = _write(tmp_path, "old.json", {"type": "object"})
    new = _write(tmp_path, "new.json", {"type": "object", "if": {}})
    assert main([str(old), str(new)]) == 0
    assert "UNKNOWN /if unsupported_keyword" in capsys.readouterr().out
    assert main([str(old), str(new), "--strict"]) == 1


def test_invalid_json_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = _write(tmp_path, "good.json", {})
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert main([str(good), str(bad)]) == 2
    assert "invalid_json" in capsys.readouterr().err


def test_missing_file_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "missing.json"
    assert main([str(missing), str(missing)]) == 2
    assert "cannot read input" in capsys.readouterr().err


def test_oversized_file_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    max_bytes = 10_000_000
    big = tmp_path / "big.json"
    big.write_bytes(b" " * (max_bytes + 1))
    assert main([str(big), str(big)]) == 2
    assert "input_too_large" in capsys.readouterr().err


def test_too_deep_and_unsupported_ref_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    deep = tmp_path / "deep.json"
    deep.write_text('{"a":' * 64 + "{}" + "}" * 64, encoding="utf-8")
    assert main([str(deep), str(deep)]) == 2
    assert "too_deep" in capsys.readouterr().err
    ref = _write(tmp_path, "ref.json", {"properties": {"x": {"$ref": "#node"}}})
    assert main([str(ref), str(ref)]) == 2
    assert "unsupported_ref" in capsys.readouterr().err


def test_argument_errors(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["only-one.json"]) == 2
    assert main(["a.json", "b.json", "--mode", "sideways"]) == 2
    assert main(["--help"]) == 0
    assert "schema-compat" in capsys.readouterr().out


def test_module_entry_point(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schema = _write(tmp_path, "s.json", {})
    monkeypatch.setattr(sys, "argv", ["schema-compat", str(schema), str(schema)])
    with pytest.raises(SystemExit) as info:
        runpy.run_path(str(entry.__file__), run_name="__main__")
    assert info.value.code == 0
