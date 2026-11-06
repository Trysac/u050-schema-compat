# schema-compat

[![PyPI version](https://img.shields.io/pypi/v/trysac-schema-compat)](https://pypi.org/project/trysac-schema-compat/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-schema-compat)](LICENSE)
[![CI](https://github.com/Trysac/u050-schema-compat/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u050-schema-compat/actions/workflows/ci.yml)

Detect breaking changes between two JSON Schema versions of an event under backward, forward or full compatibility, with JSON pointer paths

## Problem

Event producers change JSON Schemas and break consumers in production because nobody checks
compatibility in CI. Schema registries do this for Avro and Protobuf, but plain JSON Schema events
usually have no gate, and naive diffs confuse annotations such as `default` with validation. This
CLI compares two schema versions with explicit validation semantics, classifies each change and
fails the build on incompatible ones.

## Install

```sh
pip install trysac-schema-compat
# or
uv add trysac-schema-compat
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
from pathlib import Path

from schema_compat import Mode, diff, is_compatible, load_schema, render

old = load_schema(Path("old.json"))
new = load_schema(Path("new.json"))
changes = diff(old, new, Mode.FULL)
print(render(changes, "text"))
raise SystemExit(0 if is_compatible(changes, strict=True) else 1)
```

```sh
schema-compat OLD.json NEW.json --mode full --strict --format json
```

Options: `--mode backward|forward|full` (default backward), `--strict`, `--format text|json`.
Text lines look like `<SEVERITY> <path> <kind>: <detail>`. JSON output is an array of objects with
keys `path`, `kind`, `severity`, `direction`, `detail`, sorted by `(path, kind)`.

### Exit codes

- `0`: compatible (UNKNOWN findings fail only with `--strict`)
- `1`: breaking for the selected mode
- `2`: invalid JSON, input too large, nesting too deep, unsupported `$ref` or other errors

## Semantics

A change is BREAKING for a direction when some instance valid under the writer schema is invalid
under the reader schema. BACKWARD: reader = new, writer = old. FORWARD: reader = old, writer = new.
FULL checks both; each change carries the direction that breaks.

`default`, `title`, `description` and `examples` are annotations and never affect compatibility.

Assumption: properties not declared in an open object (`additionalProperties` absent or `true`) are
assumed absent in real data.

### Supported subset (drafts 07 and 2020-12)

`type`, `properties`, `required`, `additionalProperties`, `items` (single schema), `enum`, `const`,
`minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum` (numeric form), `minLength`,
`maxLength`, `minItems`, `maxItems`, local `$ref` (`#` or `#/...` pointers) and boolean schemas.
Other keywords (`oneOf`, `anyOf`, `if/then/else`, `patternProperties`, `dependentSchemas`,
`prefixItems`) are reported as `unsupported_keyword` with severity UNKNOWN when they differ,
including when a `$ref` inside them points to a changed definition.

### Change kinds

`property_added`, `property_removed`, `required_added`, `required_removed`, `type_changed`,
`enum_changed`, `constraint_changed`, `additional_properties_changed`, `schema_changed`,
`unsupported_keyword`.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
