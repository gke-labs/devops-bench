# AGENTS.md

Guidance for coding agents (and humans) working in this repository. This file is
tool-agnostic; it follows the cross-tool [AGENTS.md](https://agents.md) convention.

## Generating benchmark tasks

The repeatable procedure for turning a row of the expert task catalog into a
runnable `task.yaml` lives in **[`docs/task-generation/`](docs/task-generation/)**,
which is the source of truth:

- [`methodology.md`](docs/task-generation/methodology.md) — the spec: schema,
  directory/naming conventions, `task_id` allocation, `expected_output` rules,
  task classes, and the kind/MCP live-cluster gap. **Read this first.**
- [`catalog.md`](docs/task-generation/catalog.md) — the expert task catalog
  (source of truth) and generation-status tracker.
- [`running.md`](docs/task-generation/running.md) — running tasks locally vs. full,
  and building a model leaderboard.

### Procedure (summary — methodology is authoritative)

1. Pick a catalog row in `docs/task-generation/catalog.md`; note its name, prompt,
   success metric, category, difficulty.
2. Classify it (`manifest-generation` | `investigation` | `live-action` |
   `plan-only`) — this decides runnability and whether an `infrastructure` block
   is needed (methodology §9).
3. Choose the provider dir: `tasks/generic/` (cloud-agnostic) or `tasks/gcp/`
   (GCP/GKE-specific). Slug = kebab-case of the task name.
4. Allocate `task_id = 1000 + <row#>` (stable, idempotent, collision-free).
5. Write `tasks/<provider>/<slug>/task.yaml`: `task_id`, `name`, `prompt`
   (placeholders per §11), and an `expected_output` whose `critical requirements:`
   bullets are atomic and derived from the catalog's Success Metric, leading with
   an `Expected Tool Call:` line. Manifest tasks include a golden
   `Expected Manifest Generated:` block. Add metadata: `category`, `difficulty`,
   `task_class`, `source: catalog#<row#>`.
6. Add any fixtures (e.g. a broken manifest for an investigation task) in the
   same directory.
7. Validate the task loads:
   ```bash
   python3 -c "from pkg.evaluator.loader import load_from_tasks_dir; \
     print([(t['task_id'], t['name']) for t in load_from_tasks_dir('tasks')])"
   ```
8. Optionally smoke-test manifest/plan tasks (see `running.md`). Investigation and
   live-action tasks can't be fairly run without a cluster MCP toolserver.
9. Update the generation-status table in `catalog.md`.

### Conventions

- One requirement per `expected_output` bullet; split compound requirements.
- Phrase requirements from the catalog's Success Metric — it is ground truth.
- Keep `task_id`s globally unique; never reuse the 1–12 range used by the
  hand-authored tasks in `tasks/` and `complextasks/`.
- Don't confuse `skills/` (LLM-as-judge **rubrics**, read by
  `pkg/evaluator/evaluate.py`) with task authoring — they are unrelated.
- Don't invent OpenTofu stacks; reuse `tf/prebuilt/{kind,minimum,secret-rotation}`
  or flag that a new fixture stack is needed.
