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

**Infrastructure** — the OpenTofu deployer targets these cloud providers (set `INFRA_PROVIDER`):

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

## Adding a benchmark task

New tasks live under `tasks/<provider>/<name>/task.yaml`, each pairing a `chaos_spec` (what breaks) with a `verification_spec`/`expected_output` (how it's graded). The `tests/` directory is reserved for the Python codebase's own unit tests — it is not where benchmark task definitions go. The full schema, placeholders, and worked examples are in [docs/how-to/add-a-task.md](docs/how-to/add-a-task.md) — read that before you start.

### Best practices for new tasks

1. **Design realistic, focused failure modes in `chaos_spec`.**
   - *Single root cause:* unless you're deliberately building an advanced multi-stage cascading scenario, each `chaos_spec` should model exactly one realistic failure or stress mechanism (a traffic spike, a pod kill, injected latency).
   - *Clear parameters:* `qps`, `duration`, and disruption targets should reflect realistic production conditions without overwhelming the host running the eval.
2. **Balance deterministic and LLM-as-judge evaluation.** Put every objective, concrete assertion — HTTP status, latency thresholds, error-rate ceilings, `kubectl get` readiness — in `verification_spec`. Use LLM-as-judge grading (via `expected_output` and the judge metrics) for things that need reasoning, like an agent's diagnostic summary or incident-triage notes. Combining hard state checks with judged reasoning gives a more reliable score than either alone.
3. **Ensure cleanup.** Deployer and validation logic must leave the cluster/project clean so the next run starts fresh — see [Key considerations](docs/how-to/add-a-task.md#key-considerations) in the task how-to for why Terraform-native resources beat ad-hoc shell scripts here.
4. **Use lightweight, fast-pulling manifests.** Use small base images (`alpine`, `busybox`, `nginx:alpine`) in your task manifests, and avoid depending on the open internet or third-party APIs during validation — stub or seed what you need inside the cluster instead.
5. **Keep tasks organized and discoverable.** File each task under the provider directory that matches its deployer (`gcp`, `kind`, `noop`, or `common`), give it a globally unique `task_id`, and use a descriptive `name` — there's no formal difficulty/category field today, so naming and placement are how reviewers and other contributors scope a task at a glance.
6. **Adhere to code quality and licensing standards.** Any Python helper or deployer module you add needs the Apache 2.0 header and explicit type hints on every function. Run `uv run ruff check --fix && uv run ruff format` before opening a PR.

Before submitting, run the `task-review` skill over your task — see [the skills overview](docs/getting-started.md#skills-in-this-repo).

## Documentation

We welcome contributions around adding new tasks, models or agent harness. You can review documentation in [`docs/`](docs/README.md) for detailed instructions and skills. Start with [Getting started](docs/getting-started.md), then browse the component docs and
how-to guides from the [documentation index](docs/README.md).

## License

Apache 2.0 — see [`LICENSE`](LICENSE).
