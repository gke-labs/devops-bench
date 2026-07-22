# Design: Unified Token Accounting

## Problem statement

Every agent harness reports token usage in its own provider's terms, and
`results/normalize.py` flattens whatever it hands back to just `input` / `output`
on the dashboard row — dropping `cached`, `total`, and any reasoning count. This
makes per-task token columns comparable only *within* a harness, never *across*
them, and it blocks a stacked input/cache/output usage chart of the kind
leaderboards such as
[Artificial Analysis](https://artificialanalysis.ai/agents/coding-agents) publish.

Two systematic distortions exist today:

1. **`input` means different things per provider.** Anthropic's `input_tokens`
   counts only the *uncached* prompt, while OpenAI's `prompt_tokens` and Gemini's
   `prompt_token_count` count the *full* prompt including cache hits. A raw
   `input` comparison therefore under-reports harnesses that split cached out and
   over-reports those that fold it in — and with prompt caching on, cached tokens
   are the majority of a multi-turn run's prompt.
2. **Reasoning tokens are inconsistently bucketed.** Some providers report
   thinking tokens separately; some harnesses fold them into `output`. Rows from
   different harnesses (or eras) disagree on what `output` contains.

**Goal:** one canonical token schema that every harness maps onto, so that
(a) `input` / `cached` / `output` mean the same thing everywhere, (b) the row
schema carries them through to the leaderboard, and (c) a stacked
input/cache/output chart is a straight read off the row.

**Status:** implemented for the shared schema (`agents/result.py`), the `api`
and `gemini` harnesses, the row layer (`normalize.py` / `ResultRow` /
`schema.d.ts` / ingest validation). The `antigravity` harness emits the shape
via its own decoder (switching it to the shared helper is a one-line follow-up
once both changes land); `openclaw` passes provider-native usage through, which
the normalizer's aliases still flatten (`cached`/`reasoning` stay `None` until
it is canonicalized). The stacked chart itself is follow-up dashboard work.

## The canonical schema

Every harness returns `AgentResult.tokens` in this shape. Missing buckets are
`None` — never `0` — so the row can distinguish "not reported" from a genuine
zero:

```python
{
    "input":       int | None,  # non-cached prompt tokens
    "cached":      int | None,  # cache-read tokens
    "cache_write": int | None,  # cache-creation tokens (provider-dependent)
    "reasoning":   int | None,  # thinking / thoughts tokens
    "output":      int | None,  # visible response tokens (excludes reasoning)
    "total":       int | None,  # full footprint: sum of all buckets
}
```

Invariant: when all parts are present,
`total == input + cached + (cache_write or 0) + (reasoning or 0) + output`.
The load-bearing rule is that **`input` excludes cached tokens** — the convention
Anthropic's API already uses and the one usage leaderboards report.

The `antigravity` harness already emits this shape (harness-local; see
`agents/cli/antigravity/parsing.py`). This design promotes it to the shared
contract.

## Per-provider normalization

Provider conventions, verified against provider docs and SDKs:

| Provider | Native input | Cached relationship | Non-cached `input` = |
| --- | --- | --- | --- |
| **Anthropic** | `input_tokens` | excluded — `input`, `cache_read`, `cache_creation` are mutually exclusive | `input_tokens` (as-is) |
| **OpenAI / Ollama** | `prompt_tokens` | included — `prompt_tokens_details.cached_tokens` is a subset | `prompt_tokens − cached_tokens` |
| **Gemini** | `prompt_token_count` | included — `cached_content_token_count` is a subset ("when `cached_content` is set, this also includes the number of tokens in the cached content") | `prompt_token_count − cached_content_token_count` |

Per-harness mapping onto the schema:

| Harness | `input` | `cached` | `cache_write` | `reasoning` | `output` |
| --- | --- | --- | --- | --- | --- |
| `api` (Anthropic) | `input_tokens` | `cache_read_input_tokens` | `cache_creation_input_tokens` | `None` (billed inside output) | `output_tokens` |
| `api` (Gemini) | `prompt_token_count − cached_content_token_count` (+ `tool_use_prompt_token_count`) | `cached_content_token_count` | `None` | `thoughts_token_count` | `candidates_token_count` |
| `api` (OpenAI) | `prompt_tokens − cached_tokens` | `cached_tokens` | `None` (SDK does not surface it) | `completion_tokens_details.reasoning_tokens` | `completion_tokens` |
| `gemini` CLI | CLI stats input − cached | CLI stats cached | `None` | thoughts (when surfaced) | CLI stats output |
| `openclaw` | provider-dependent (as `api`) | provider-dependent | `None` | provider-dependent | provider-dependent |
| `antigravity` | already canonical (decoded from the conversation DB) | ✓ | `None` | ✓ | ✓ |

Notes:

- `cache_write` is populated only where the provider reports it (Anthropic).
  Everywhere else it is `None`, which the schema distinguishes from `0`.
- Where a provider's cached-inclusion convention cannot be confirmed for a given
  surface, do **not** blind-subtract: assert the sum invariant against the
  provider `total` and fall back to reporting the native input with
  `cached=None`.
- Keyless/OAuth surfaces that expose no cache telemetry report `cached=None`
  and the full prompt as `input` — faithful, since no split is observable.

## Row layer and the chart

`results/normalize.py::normalize_tokens` currently returns `(input, output)`
only. This design widens the row contract:

- Add `cached_tokens` / `reasoning_tokens` / `cache_write_tokens` /
  `total_tokens` to `ResultRow` — additive nullable fields, so no
  `SCHEMA_VERSION` bump is needed and historical rows stay valid. All four
  cost-formula inputs (`input·p_in + cached·p_cached + cache_write·p_write +
  output·p_out`) are then readable off the row.
- Add `cached` / `reasoning` aliases to the normalizer's key tables; keep the
  existing aliases for historical `results.json` files.
- Mirror the fields on the dashboard `ResultRow` interface and accept them
  (absent-tolerant) in the ingest validator; the stacked
  `input` / `cached` / `output` bar per model × harness arm is follow-up
  dashboard work.

Because `input` is non-cached everywhere, the stacked total is the true per-task
footprint and is finally comparable across harnesses.

## Shared schema location

The bucket tuple and `empty_tokens()` helper live in `agents/result.py`, and
each harness's extractor returns the canonical dict. Extraction stays
per-harness (each reads a different surface); only the output shape is shared.
The `antigravity` harness's local copy folds into the shared helper once both
changes land.

## Migration / compatibility

- **Historical rows** have no `cached` column; the chart treats a missing
  `cached` as "telemetry unavailable" (empty segment), not zero.
- **Mixed-era `output`**: harnesses that previously folded reasoning into
  `output` will show a step change when reasoning splits out. The row's new
  `reasoning_tokens` column makes the old quantity recoverable
  (`output + reasoning`).
- The `AgentResult.tokens` shape is provider-defined by contract, so widening it
  is not a breaking harness-interface change; only parsers, the normalizer, and
  the row schema change.

## Open questions

- **Chart segments**: stack `cache_write` / `reasoning` as extra segments, or
  keep them row-only for cost math? They are populated unevenly across
  providers.
- **`total` source of truth**: provider-reported total vs. the recomputed sum
  (they can disagree where a provider rolls extras into its total).
- **Raw usage retention**: keep the untouched provider usage alongside the
  canonical dict (e.g. under `metadata`) so historical runs can be re-priced
  when provider pricing or cache accounting changes.
