# devops-bench

devops-bench is a benchmark for AI agents that do real, end-to-end DevOps work — provisioning clusters, fixing broken deployments, shipping workloads. It's Kubernetes-centric (and cloud-native more broadly), and it measures whether an agent actually achieves the outcome, not just whether it writes plausible-looking YAML or code.

Most benchmarks stop at "did the model produce reasonable text?" This one runs the agent against live infrastructure and checks the result. It also lets you quantify the payoff of giving agents more to work with — context, operational rules, and tools like MCP servers and skills — so you can see what those additions are actually worth.

## How it works

For each task, the harness provisions real infrastructure if the task needs it (OpenTofu spins up a GKE cluster or a local kind cluster), runs your agent against it, optionally injects chaos and verifies the resulting cluster state, then scores the run with LLM-as-judge metrics — and tears everything down when it's done.

A single run, end to end:

1. **Provision** — OpenTofu stands up GKE or kind (or nothing, for manifest-only tasks).
2. **Run the agent** — your chosen agent harness drives the task.
3. **Chaos + verify** — optionally break things, then check the live cluster state.
4. **Score** — LLM-as-judge metrics grade the outcome and the agent's tool use.
5. **Teardown** — everything provisioned is cleaned up.

## What's supported

**Agent harnesses** — choose with `BENCH_AGENT_TYPE` or `--agent-type`:

| Key | What it runs |
| :-- | :-- |
| `gemini` | The Google Gemini CLI. |
| `openclaw` | The Openclaw Agent CLI. |
| `api` | In-process: drives a provider SDK directly through a model-agnostic MCP tool loop. |

**Model providers** — choose with `AGENT_PROVIDER` and `AGENT_MODEL`:

| Key | Backends |
| :-- | :-- |
| `gemini` | Google AI Studio API key, or Vertex AI. |
| `claude` | Anthropic API, Vertex AI, or Bedrock. |
| `ollama` | Local models. |

**Infrastructure** — the OpenTofu deployer targets these cloud providers (set `CLOUD_PROVIDER`):

| Key | Target |
| :-- | :-- |
| `gcp` | GKE. |
| `kind` | Local KinD clusters. |
| `noop` | No provisioning — run against a pre-existing cluster. |

## Install

You need Python 3.12 or newer. The project uses [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --extra all
```

Provider SDKs are optional extras, so you can install just what you use: `google-genai`, `anthropic`, `openai`, or `all`. The pip equivalent:

```bash
pip install ".[all]"
```

## Run your first eval

Here's a no-infra task scored by a judge — no cloud account or cluster required. It asks the agent to produce a Kubernetes Deployment, then grades the result with an LLM judge:

```bash
BENCH_NO_INFRA=true \
AGENT_PROVIDER=gemini AGENT_MODEL=gemini-3.1-pro-preview AGENT_API_KEY=$GEMINI_KEY \
JUDGE_PROVIDER=gemini JUDGE_MODEL=gemini-3.1-pro-preview JUDGE_API_KEY=$GEMINI_KEY \
python -m devops_bench --no-infra tasks/noop/create-deployment/task.yaml
```

Results land in `results/run_<timestamp>/`, with `results.json` (full scored output), `rows.json` (flattened, ingest-ready rows), and `manifest.json` (run metadata).

**Working through a coding agent?** Instead of assembling the command yourself, point it at the `run-eval` skill — it picks local vs bastion, sets up auth, launches, and watches the run for you. See [the skills overview](docs/getting-started.md#skills-in-this-repo).

For real GKE/kind runs and parallel matrices, see the [run-evals how-to](docs/how-to/run-evals.md).

## Live results

See the latest scores on the [leaderboard](https://gke-labs.github.io/devops-bench/).

## Documentation

Full documentation lives in [`docs/`](docs/README.md). Start with
[Getting started](docs/getting-started.md), then browse the component docs and
how-to guides from the [documentation index](docs/README.md).

## License

Apache 2.0 — see [`LICENSE`](LICENSE).
