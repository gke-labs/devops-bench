# Model providers

devops-bench can drive an agent, a judge, and a chaos agent with different LLMs,
and it does so through one small interface. Every provider implements the same
`LLMClient` contract (`devops_bench/models/base.py`), and a single factory,
`get_model()`, constructs the right adapter at runtime. Add a provider by
dropping a file in `devops_bench/models/`; nothing else in the tree needs to
change.

> [!IMPORTANT]
> This page is about the **LLM** that powers the agent under test and the judge
> — not the **cloud** your benchmark infrastructure runs on. Those are separate
> concerns. A run can use Claude on Anthropic's API while provisioning Google
> Cloud resources, for example. For the cloud/infra side, see
> [infra.md](./infra.md).

## Supported providers and models

A provider key selects an adapter. Aliases are alternate spellings that resolve
to the same adapter. Backends are the transports a single adapter can reach,
chosen at runtime from the environment.

| Provider key | Aliases | Backends | Default model | SDK / install extra |
| --- | --- | --- | --- | --- |
| `gemini` | `google`, `google-vertex`, `google_vertex` | Google AI Studio API key, Vertex AI | `gemini-3.1-pro-preview` | `google-genai` |
| `claude` | `anthropic` | Anthropic API, Vertex AI, Amazon Bedrock | backend-specific (`api` → `claude-sonnet-4-5`; Bedrock requires `AGENT_MODEL`) | `anthropic` |
| `ollama` | — | local OpenAI-compatible server | `gemma4:2b` | `openai` |

A few things worth calling out:

- **`google-vertex` is not a separate adapter.** It is an alias that resolves to
  the `gemini` adapter, which then picks Vertex AI at runtime based on the
  environment (a `GCP_PROJECT_ID` with no API key). There is no distinct Vertex
  module.
- **Install extras are named by PyPI package, not by provider key.** The extras
  are `google-genai`, `anthropic`, `openai`, and `all` — a different axis from
  the provider keys above. The most surprising consequence: the `openai` extra
  is what backs the `ollama` provider, because the Ollama adapter talks to its
  server through the `openai` client. Install the SDK you need:

  ```bash
  pip install "devops-bench[google-genai]"   # gemini
  pip install "devops-bench[anthropic]"       # claude
  pip install "devops-bench[openai]"          # ollama
  pip install "devops-bench[all]"             # everything
  ```

## How a model is selected

There are three roles, and each reads its own environment variables.

| Role | Provider var | Model var | Notes |
| --- | --- | --- | --- |
| Agent under test | `AGENT_PROVIDER` | `AGENT_MODEL` | Also `AGENT_API_KEY`, `AGENT_MAX_TOKENS`. |
| Judge | `JUDGE_PROVIDER` | `JUDGE_MODEL` | Also settable via the `--judge-provider` / `--judge-model` CLI flags. |
| Chaos agent | `CHAOS_PROVIDER` | `CHAOS_MODEL` | Falls back to `AGENT_PROVIDER` / `AGENT_MODEL` when unset. |

When no provider is given anywhere, `get_model()` defaults to `gemini`.

### Backend-selecting variables

Within a provider, these variables choose the transport:

| Variable | Effect |
| --- | --- |
| `GCP_PROJECT_ID` + `GCP_VERTEX_LOCATION` | Selects Vertex AI for both `gemini` and `claude`. `GCP_VERTEX_LOCATION` defaults to `global`. |
| `ANTHROPIC_BACKEND` | Forces the Claude backend: `api`, `vertex`, or `bedrock`. Overrides the inference below. |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | Selects the Claude Bedrock backend. |
| `OLLAMA_BASE_URL` | Endpoint for the Ollama server (defaults to `http://localhost:11434/v1`). |

For Claude, if you don't force `ANTHROPIC_BACKEND`, the adapter infers a backend:
an API key (`AGENT_API_KEY` / `ANTHROPIC_API_KEY`) selects `api`, then
`GCP_PROJECT_ID` selects `vertex`, then an AWS region selects `bedrock`, with
`vertex` as the final fallback.

> [!NOTE]
> When the agent harness is a CLI (the `gemini` or `openclaw` agents),
> `AGENT_PROVIDER` / `AGENT_MODEL` / `AGENT_API_KEY` are mapped onto that CLI's
> own environment variables instead of going through `get_model()`. For example,
> the gemini CLI agent receives `GEMINI_MODEL`, `GOOGLE_API_KEY`, and
> `GEMINI_API_KEY`. Only the `api` harness calls `get_model()` directly. This
> per-harness divergence is a known inconsistency we plan to unify (tracked in
> [#147](https://github.com/gke-labs/devops-bench/issues/147)). See
> [agents.md](./agents.md) for how each harness consumes its config today.

## Configuration examples

These are copy-pasteable. Set the variables in your shell (or in whatever you use
to launch a run) before invoking the benchmark.

**Gemini via AI Studio (API key):**

```bash
export AGENT_PROVIDER=gemini
export AGENT_MODEL=gemini-3.1-pro-preview
export AGENT_API_KEY="$YOUR_AI_STUDIO_KEY"
```

**Gemini on Vertex AI (no key — uses ADC + project):**

```bash
export AGENT_PROVIDER=gemini
export AGENT_MODEL=gemini-3.1-pro-preview
export GCP_PROJECT_ID=my-gcp-project
export GCP_VERTEX_LOCATION=global
# No AGENT_API_KEY: the adapter uses Application Default Credentials.
```

**Claude via the first-party Anthropic API:**

```bash
export AGENT_PROVIDER=claude
export AGENT_MODEL=claude-sonnet-4-5
export AGENT_API_KEY="$YOUR_ANTHROPIC_KEY"
```

**Claude on Vertex AI:**

```bash
export AGENT_PROVIDER=claude
export ANTHROPIC_BACKEND=vertex
export AGENT_MODEL=claude-sonnet-4-5@20250929
export GCP_PROJECT_ID=my-gcp-project
export GCP_VERTEX_LOCATION=global
```

**Ollama (local server):**

```bash
export AGENT_PROVIDER=ollama
export AGENT_MODEL=gemma4:2b
export OLLAMA_BASE_URL=http://localhost:11434/v1
```

## Adding a provider

To add your own provider — including the adapter file-naming convention and how
aliases resolve — see [Add a model provider](../how-to/add-a-model-provider.md).
