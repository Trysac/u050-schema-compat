# Compare schemas with reader/writer set-inclusion semantics

Status: accepted (generated, pending human review)

## Context

Event schemas change without a compatibility gate and naive diffs confuse annotations such as default with validation. We need a deterministic CLI and library that classifies each change for backward, forward or full compatibility, with JSON pointer paths, using only the standard library.

## Decision

A change is breaking when an instance valid under the writer schema is invalid under the reader schema. One comparison check(reader, writer) implements everything: BACKWARD uses reader=new and writer=old, FORWARD swaps the arguments and FULL merges both runs, marking the direction that breaks. Only a documented subset of JSON Schema is analysed; other keywords that differ are reported as UNKNOWN and fail only with --strict. Local $ref pointers are resolved per RFC 6901, comparisons are memoised on pointer pairs with a coinductive assumption for cycles, and every input is bounded by size, depth and pair limits with a single typed error class.

## Consequences

Results are explainable and symmetric between modes, annotations never affect the verdict, and recursive schemas terminate. Unsupported constructs are never silently treated as compatible. The cost is a conservative analysis: some equivalent rewrites of unsupported keywords are reported as UNKNOWN, a subschema pair reached through several references is reported once, and properties undeclared in open objects are assumed absent in data.
