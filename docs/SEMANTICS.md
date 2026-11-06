# Compatibility semantics

`schema-compat` compares two JSON Schema versions (drafts 07 and 2020-12, supported subset) and
classifies every difference.

## Definitions

A change is BREAKING for a direction when some instance valid under the writer schema is invalid
under the reader schema.

| Mode | Reader | Writer |
|---|---|---|
| BACKWARD | new | old |
| FORWARD | old | new |
| FULL | both directions | each change carries the direction that breaks (`backward`, `forward` or `both`) |

One comparison `reader` against `writer` implements everything; FORWARD swaps the arguments.
Severities are `COMPATIBLE`, `BREAKING` and `UNKNOWN` (a construct the tool does not analyse).

## Supported subset

`type` (strings or arrays, `integer` is a subset of `number`), `properties`, `required`,
`additionalProperties` (boolean or schema, compared recursively), `items` (single schema),
`enum`, `const`, `minimum`, `maximum`, `exclusiveMinimum` and `exclusiveMaximum` (numeric form
only), `minLength`, `maxLength`, `minItems`, `maxItems`, local `$ref` and the boolean schemas
`true` and `false`.

`default`, `title`, `description`, `examples` and similar keywords are annotations and never
affect compatibility. Any other keyword that differs (`if`, `then`, `else`, `patternProperties`,
`dependentSchemas`, `prefixItems`, `oneOf`, `anyOf`, `allOf`, `format`, `pattern`, ...) produces
`unsupported_keyword` with severity `UNKNOWN`; equal values are compatible. `UNKNOWN` fails the
CLI only with `--strict`.

## Change kinds

`property_added`, `property_removed`, `required_added`, `required_removed`, `type_changed`,
`enum_changed`, `constraint_changed`, `additional_properties_changed`, `schema_changed` (boolean
schemas and `const`) and `unsupported_keyword`.

Paths are JSON pointers into the new schema (the old schema for removals). Required changes are
reported at the object pointer plus `/required`.

## Assumptions

* Properties that are not declared in an open object (`additionalProperties` absent or `true`)
  are assumed absent in real data. Adding an optional property is therefore compatible, and a
  removed property is breaking only for the reader that closes the object
  (`additionalProperties: false`) or restricts additional properties with a schema.
* Changing `additionalProperties` itself (for example open to closed) is compared strictly.
* `enum` and `const` use JSON equality: `1` equals `1.0`, booleans equal only booleans, arrays
  compare by order and objects by keys and values.
* Lower and upper bounds combine the inclusive and exclusive keywords into one effective bound.

## References

Only local references are supported. The fragment is percent-decoded and resolved as an RFC 6901
pointer in the same document (`#`, `#/$defs/a~1b`, `#/$defs/a%20b`, `#/definitions/x`).
Other files, URLs and `#anchor` names raise `unsupported_ref`. Boolean `exclusiveMinimum` and
`exclusiveMaximum` raise `invalid_schema`.

Comparisons are memoised on the pair of referenced pointers (at most 100000 pairs, otherwise
`too_complex`). A pair already being compared is assumed compatible, so recursive schemas
terminate. A pair reached through several references is reported once, at the first path where it
is met. Keywords next to a `$ref` are compared for equality only.

## Limits and errors

`load_schema` enforces `max_bytes` (default 10000000) and `max_depth` (default 64). Nesting depth
is checked iteratively after parsing and `RecursionError` maps to `too_deep`. All failures raise
`SchemaCompatError` with a stable `code`: `invalid_json`, `input_too_large`, `too_deep`,
`unsupported_ref`, `invalid_schema` or `too_complex`. Messages quote at most 200 characters.

## CLI

```
schema-compat OLD.json NEW.json [--mode backward|forward|full] [--strict] [--format text|json]
```

Text lines look like `<SEVERITY> <path> <kind>: <detail>`. JSON output is an array of objects
with the keys `path`, `kind`, `severity`, `direction` and `detail`, sorted by `(path, kind)`.
Exit codes: 0 compatible, 1 breaking for the selected mode (or unknown with `--strict`), 2 for
unreadable or invalid input and invalid arguments.

## Out of scope

Full JSON Schema semantics, Avro, Protobuf and schema registries.
