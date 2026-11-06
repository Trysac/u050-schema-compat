# schema-compat

[![PyPI version](https://img.shields.io/pypi/v/trysac-schema-compat)](https://pypi.org/project/trysac-schema-compat/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-schema-compat)](LICENSE)
[![CI](https://github.com/Trysac/u050-schema-compat/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u050-schema-compat/actions/workflows/ci.yml)

Detect breaking changes between two JSON Schema versions of an event under backward, forward or full compatibility, with JSON pointer paths

## Problem

Describe in two or three sentences the concrete problem this utility solves, who hits it, and what
they do today without it. Replace this paragraph when the first real feature lands.

## Install

```sh
pip install trysac-schema-compat
# or
uv add trysac-schema-compat
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
import schema_compat

# normalize() trims surrounding whitespace and lower-cases the text.
print(schema_compat.normalize("  Hello World "))  # -> "hello world"

# Blank input is rejected explicitly instead of returning an empty string.
try:
    schema_compat.normalize("   ")
except ValueError as exc:
    print(f"rejected: {exc}")
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
