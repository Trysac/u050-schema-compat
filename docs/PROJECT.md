# Project record

## Objective

Detect breaking changes between two JSON Schema versions of an event under backward, forward or full compatibility, with JSON pointer paths

## Scope

- In scope: the public API documented in [README.md](../README.md), typed and tested.
- Out of scope: anything that needs runtime dependencies or I/O without an accepted ADR.

## Timeline

| Date | Event |
|---|---|
| 2026 | Repository created from the factory utility template. |

## Effort metrics

Measured values only; a value that has not been measured stays "pending measurement".

| Metric | Value |
|---|---|
| Tokens (input / output) | 502533 / 144589 |
| Hours (human) | pending measurement |
| Cost (USD) | 1.0968 |

## Factory run u050 (measured from API usage)

| Phase | Model | Batch | Input | Output | Cache write | Cache read | Cost (USD) |
|---|---|---|---|---|---|---|---|
| generation | claude-sonnet-5-5 | yes | 2754 | 124720 | 0 | 4246 | 0.6268 |
| fix-1 | claude-sonnet-5-5 | no | 10 | 2553 | 14625 | 92107 | 0.0713 |
| audit | claude-sonnet-5-5 | no | 14 | 8996 | 50670 | 170807 | 0.2337 |
| fix-2 | claude-sonnet-5-5 | no | 10 | 3540 | 13734 | 82617 | 0.0780 |
| docs | claude-haiku-5-5 | no | 149968 | 4780 | 0 | 0 | 0.0869 |

Total: $1.0968. Prices: Anthropic list prices.
