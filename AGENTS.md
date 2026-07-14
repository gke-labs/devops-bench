# devops-bench

devops-bench is a benchmark that evaluates AI agents on real, end-to-end DevOps tasks:
provision infra → run the agent → optional chaos + verify → judge → teardown.

## Where things live

| Path | What it is |
| --- | --- |
| `devops_bench/` | The canonical pipeline. Subpackages: `core/`, `models/`, `providers/`, `deployers/`, `agents/`, `chaos/`, `verification/`, `metrics/`, `evalharness/`, `tasks/`, `results/`. |
| `tasks/` | Task definitions on disk (`task.yaml` files). |
| `tf/` | OpenTofu / Terraform infrastructure modules. |
| `site/` | React + Vite leaderboard plus the Firestore `ingest/` pipeline. |
| `docs/` | Human documentation. |
| `.agents/skills/` | Skills for coding agents. |

## Commands

```bash
uv sync --extra all                 # install runtime + dev + every provider SDK
uv run pytest                       # tests
uv run ruff check .                 # lint
uv run ruff format .                # format
# run one eval quickly (no cloud, no credentials):
BENCH_NO_INFRA=true python -m devops_bench --no-infra tasks/noop/create-deployment/task.yaml
```

For Task × Model × AgentConfig matrices, use the `run-parallel-evals` skill.

## Conventions

- **Python ≥ 3.12 + uv.** Ruff rule sets `E,F,I,UP,B,SIM`, line length 100.
- **Google-style docstrings.**
- **Minimal, self-documenting code** — comments only for edge cases or non-obvious intent, never to narrate code.
- `devops_bench/` is the canonical path. Ignore any legacy `pkg/`.
- **Tasks are graded on outcome, not method** — accept every valid path to the goal.
- **Parallel-safety is critical.** Every globally-unique cloud resource name must be
  run-scoped and swept at teardown, so concurrent runs never collide. See the task-review skill.
- After changing code, run the **docs-sync** skill and log any new run-time failure to
  `docs/appendix/known_issues.md`.

## Docs

- `docs/README.md` — documentation index.
- `docs/getting-started.md` — dev environment, how evals run, the skills.
- `docs/components/architecture.md` — eval lifecycle and component wiring.
- `docs/appendix/known_issues.md` — recovery router + current known hacks.

## Skills

Skills live in `.agents/skills/`. Use when:

- **run-eval** — run one eval (1 task × 1 model × 1 config); the easy entrypoint.
- **validate-eval** — validate a new eval in a self-healing loop.
- **run-parallel-evals** — run a Task × Model × AgentConfig matrix.
- **devops-bench-review** — review code changes (correctness, parallel-safety, conventions, docs).
- **task-review** — review a new task before submitting.
- **docs-sync** — keep docs current with code.
- **cleanup-orphaned-resources** — GC leaked cloud resources.
- **diagnose-eval-failure** — explain why a model failed an eval.
