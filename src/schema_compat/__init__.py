"""Detect breaking changes between two JSON Schema versions of an event."""

from __future__ import annotations

import logging

from schema_compat.engine import diff
from schema_compat.errors import SchemaCompatError
from schema_compat.loader import load_schema
from schema_compat.models import Change, Mode, Severity
from schema_compat.output import is_compatible, render

__all__ = [
    "Change",
    "Mode",
    "SchemaCompatError",
    "Severity",
    "__version__",
    "diff",
    "is_compatible",
    "load_schema",
    "render",
]

__version__ = "0.1.0"

logging.getLogger(__name__).addHandler(logging.NullHandler())
