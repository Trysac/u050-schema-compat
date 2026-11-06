"""Typed errors shared by every schema_compat module."""

from __future__ import annotations

from typing import Literal

ErrorCode = Literal[
    "invalid_json",
    "input_too_large",
    "too_deep",
    "unsupported_ref",
    "invalid_schema",
    "too_complex",
]

MAX_MESSAGE_CHARS = 200


def clip(text: str, limit: int = MAX_MESSAGE_CHARS) -> str:
    """Return ``text`` shortened to at most ``limit`` characters."""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


class SchemaCompatError(Exception):
    """Base error of the library.

    Attributes:
        code: Stable machine-readable error code.
        message: Human readable message, never longer than 200 characters.
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code: ErrorCode = code
        self.message = clip(message)
        super().__init__(self.message)
