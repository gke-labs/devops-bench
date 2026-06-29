# Getting started

Welcome! This is the doc you start with if you want to contribute to **devops-bench**. It walks you through setting up a dev environment, explains how evals actually run, and points you at the skills that help you run and review them.

## Intro

devops-bench is a benchmark suite for evaluating DevOps agents and models against real GKE/GCP tasks. As a contributor you'll mostly do three things: set up the tooling, run evals (locally for the fast path, on a bastion for the real thing), and use the repo's skills to drive and review those runs. This page covers all three so you can get productive quickly.

## Set up your dev environment

You need **Python ≥ 3.12** (the repo's `.python-version` pins 3.13) and **[uv](https://docs.astral.sh/uv/)** as the dependency manager. `uv.lock` pins the full resolution; `pyproject.toml` carries minimum-version floors. The build backend is hatchling.

Pick the install that matches what you're doing:

| Command | What you get |
| --- | --- |
| `uv sync` | Runtime deps plus the `dev` group (it's included by default). |
| `uv sync --extra all` | The above, plus every provider SDK. |
| `uv sync --frozen --extra all` | Lockfile-pinned, no resolution — the CI/Docker style. |

The `dev` dependency group ships by default and pulls in `pytest`, `pytest-mock`, `ruff`, `pre-commit`, and `devops-bench[all]`, so a plain `uv sync` already gives you the test and lint toolchain.

### Provider extras

Provider SDKs are optional and named by package. Install only what you need:

| Extra | SDK |
| --- | --- |
| `google-genai` | `google-genai` |
| `anthropic` | `anthropic` |
| `openai` | `openai` |
| `all` | all of the above |

```bash
uv sync --extra google-genai     # just the Gemini SDK
uv sync --extra all              # everything
```

### Console script

Installing the package exposes the `devops-bench` console script, which maps to `devops_bench.cli:main`. Run it through uv:

```bash
uv run devops-bench --help
```

### Pre-commit hooks

Install both the commit-time and push-time hooks:

```bash
uv run pre-commit install
uv run pre-commit install --hook-type pre-push
```

| Hook | Stage | What it does |
| --- | --- | --- |
| `ruff format` | pre-commit | Formats Python. |
| `ruff check` | pre-commit | Lints Python. |
| `uv lock --check` | pre-push | Fails if `uv.lock` is out of date. |

Ruff is configured for target `py312`, line length 100, with rule sets `E`, `F`, `I`, `UP`, `B`, and `SIM`.

### Tests

```bash
uv run pytest
```

> [!TIP]
> Use the `all` extra for the full suite — it exercises every provider adapter, so without it some tests can't import their SDK.

## The Docker image

The `Dockerfile` builds the complete eval-harness image. It installs the `devops-bench` console script and bundles the runtime toolchain that real evals drive: **OpenTofu 1.8.8**, **kubectl**, the **Google Cloud SDK** with **gke-gcloud-auth-plugin**, **Node 24** with the **Gemini CLI**, and the **gke-mcp** server.

It builds on `debian:trixie-slim` and installs Python deps with `uv sync --frozen --no-dev --extra all`. It's multi-arch: the `ARCH` build arg defaults to the host architecture, so a plain build works on both amd64 and arm64 (including an Apple-silicon `podman machine`).

Build it (Podman or Docker — they're interchangeable):

```bash
podman build -t devops-bench-harness:latest .            # or docker build
podman run --rm -v "$(pwd)/results:/app/results" \
  -e JUDGE_PROVIDER=ollama -e JUDGE_MODEL=llama3 \
  devops-bench-harness:latest tasks/noop/create-deployment/task.yaml --no-infra
```

The entrypoint forwards its args straight to the CLI, and results land on the `/app/results` bind mount.

## How evals run (what you need at runtime)

What you need depends on whether you're running the fast local path or provisioning real cloud infra.

**The fast path needs nothing extra.** Unit tests, lint/format, and harness runs with `--no-infra` all run locally against the NoOpDeployer — no cloud, no credentials.

**Real GKE/GCP evals provision a live cluster.** They need a co-located toolchain (OpenTofu, kubectl, gcloud) plus GCP credentials via Application Default Credentials (ADC). The project provides a **bastion** VM pre-loaded with all of it — see [components/bastion.md](./components/bastion.md). This matters especially for the `openclaw` agent, which is local-only: the whole harness has to run co-located on a single machine.

A subset of tasks instead run on **kind** clusters directly on the host — control-plane surgery, policy remediation, upgrades, and crashloop debugging. kind needs Docker and raised `fs.inotify` limits.

> [!WARNING]
> The bastion service account is owner-equivalent. Only ever point it at a sandbox or non-prod project.

When you're ready to run something for real, follow [how-to/run-evals.md](./how-to/run-evals.md).

## Skills in this repo

The repo ships **skills for coding agents** in `.agents/skills/` — you invoke them to run,
validate, review, and maintain evals. They are agent-agnostic (Claude Code, Antigravity, Codex);
shared mechanics live in `.agents/references/`.

| Skill | Purpose | When to use |
| --- | --- | --- |
| `run-eval` | Run one eval (1 task × 1 model × 1 config), local or bastion. | The easy entrypoint for a single run. |
| `validate-eval` | Validate a new eval in a self-healing loop until it provisions, runs, and grades correctly. | Vetting a newly added task. |
| `run-parallel-evals` | Run a Task × Model × AgentConfig matrix with monitoring, retry, and optional self-healing. | Matrices and comparisons. |
| `devops-bench-review` | Review a code change — correctness, testability, maintainability, API hygiene, domain modeling, conventions. | Reviewing a code diff. |
| `task-review` | Review a new task — schema, rubric quality, parallel-safety, infra config, leaks. | Vetting a new or changed task. |
| `docs-sync` | Update the docs a code change affects, and prune known-issues that code has fixed. | After changing code. |
| `cleanup-orphaned-resources` | Find and remove leaked cloud resources left by aborted runs. | Cleaning up after failures. |
| `diagnose-eval-failure` | Explain why a model failed an eval, from its trajectory and the judge's reasons. | Understanding a low score. |

## Where to go next

- [Run evals](./how-to/run-evals.md) — actually kick off a run.
- [Add a task](./how-to/add-a-task.md) — contribute a new benchmark task.
- [Architecture](./components/architecture.md) — how the pipeline fits together.
- [Known issues](./appendix/known_issues.md) — current rough edges.
- [Contributing](./contributing.md) — CLA and the PR process.
- [Project README](../README.md) — the high-level overview.
