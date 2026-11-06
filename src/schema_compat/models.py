"""Public data model: modes, severities and changes."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Literal

Direction = Literal["backward", "forward", "both"]


class Mode(enum.Enum):
    """Compatibility mode.

    BACKWARD: the new schema (reader) must accept data written with the old schema.
    FORWARD: the old schema (reader) must accept data written with the new schema.
    FULL: both directions.
    """

    BACKWARD = "backward"
    FORWARD = "forward"
    FULL = "full"


class Severity(enum.Enum):
    """Severity of a change."""

    COMPATIBLE = "COMPATIBLE"
    BREAKING = "BREAKING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Change:
    """One difference between two schemas.

    ``detail`` is informational text and is excluded from equality and hashing.
    ``direction`` is set only on breaking changes and names the direction that breaks.
    """

    path: str
    kind: str
    severity: Severity
    direction: Direction | None
    detail: str = field(default="", compare=False)
