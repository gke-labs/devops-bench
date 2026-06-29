# devops_bench/

The canonical pipeline. One engine runs each task through a fixed lifecycle:
provision → run agent → chaos + verify → score → teardown.

## Extend via registries — never edit the engine

Every extension axis is a registry. To add to one, write a class with its registration
decorator (or ship an entry-point package that registers itself):

| Axis | Registry |
| --- | --- |
| Agents | `AGENTS` |
| Models | `MODELS` |
| Cloud providers | `PROVIDERS` |
| Chaos faults / triggers | `FAULTS`, `TRIGGERS` |
| Verifiers | `VERIFIERS` |
| Metrics | `METRICS` |

## Layering

`core/` → {`models`, `providers`, `deployers`, `agents`, `chaos`, `verification`, `metrics`}
→ `evalharness/` (the `DefaultEvalHarness` orchestrator).

Deeper: `../docs/components/architecture.md`, `../docs/components/glossary.md`, and the
`add-a-*` how-tos under `../docs/how-to/`.
