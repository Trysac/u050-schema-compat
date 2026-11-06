"""Command line interface: ``python -m schema_compat OLD.json NEW.json``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from schema_compat import Mode, SchemaCompatError, diff, is_compatible, load_schema, render


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schema-compat",
        description="Detect breaking changes between two JSON Schema versions.",
    )
    parser.add_argument("old", type=Path, help="path of the old schema")
    parser.add_argument("new", type=Path, help="path of the new schema")
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in Mode],
        default="backward",
        help="compatibility mode (default: backward)",
    )
    parser.add_argument("--strict", action="store_true", help="also fail on UNKNOWN findings")
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["text", "json"],
        default="text",
        help="output format (default: text)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the exit code.

    0: compatible. 1: breaking for the selected mode (or unknown with --strict).
    2: unreadable or invalid input, or invalid arguments.
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    try:
        changes = diff(load_schema(args.old), load_schema(args.new), Mode(args.mode))
    except SchemaCompatError as exc:
        print(f"error [{exc.code}]: {exc.message}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: cannot read input ({type(exc).__name__})", file=sys.stderr)
        return 2
    output = render(changes, args.output_format)
    if output:
        print(output)
    return 0 if is_compatible(changes, strict=args.strict) else 1


if __name__ == "__main__":
    sys.exit(main())
