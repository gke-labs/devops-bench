# Out-of-tree task example

A complete, runnable benchmark task that lives **outside** the devops-bench repo — task
definition and OpenTofu stack both. Copy this directory into your own repo, edit it, and point
the harness at it. Nothing needs to be contributed back to devops-bench.

This is the worked example for [How to run out-of-tree tasks](../../docs/how-to/out-of-tree-tasks.md);
read that guide for the full extension surface and the gotchas.

```
out-of-tree-task/
├── noop-task.yaml   # no infra at all — start here
├── task.yaml        # provisions the stack below
└── tf/
    ├── main.tf      # self-contained kind cluster
    └── variables.tf # declares what the harness injects
```

## Run it

**1. No dependencies.** Proves an out-of-tree task file loads and grades. No cloud, no
credentials, no Docker:

```bash
BENCH_NO_INFRA=true \
AGENT_PROVIDER=gemini AGENT_MODEL=gemini-3.1-pro-preview AGENT_API_KEY=$GEMINI_KEY \
JUDGE_PROVIDER=gemini JUDGE_MODEL=gemini-3.1-pro-preview JUDGE_API_KEY=$GEMINI_KEY \
python -m devops_bench --no-infra /abs/path/to/out-of-tree-task/noop-task.yaml
```

**2. With your own Terraform.** Needs Docker and the `kind` binary. First set `stack:` in
`task.yaml` to the absolute path of the `tf/` directory beside it — stack paths are not
relative to the task file:

```bash
AGENT_PROVIDER=gemini AGENT_MODEL=gemini-3.1-pro-preview AGENT_API_KEY=$GEMINI_KEY \
JUDGE_PROVIDER=gemini JUDGE_MODEL=gemini-3.1-pro-preview JUDGE_API_KEY=$GEMINI_KEY \
python -m devops_bench --project "" --cluster oot-demo \
  /abs/path/to/out-of-tree-task/task.yaml
```

Swap the kind stack for a GCP one by changing `provider:` to `gcp` and writing a stack that
outputs `cluster_name` and `cluster_location`.

## What to change first

| Where | Why |
| --- | --- |
| `task.yaml` → `infrastructure.stack` | Must be the **absolute** path to your stack |
| `task.yaml` → `infrastructure.provider` | **Required** for an external stack — the harness will not guess it |
| `tf/variables.tf` | Declare every variable the harness injects, or it is silently dropped |
| `tf/main.tf` outputs | `cluster_name` and `cluster_location` are a hard contract |
| `prompt` / `expected_output` | Your actual scenario. Grade on outcome, not on one prescribed method |

## Notes

- Both task files use `{{...}}` placeholders for infra values. Never hardcode a cluster name or
  project — that is what lets the same task run anywhere, and in parallel.
- The `documentation:` blocks are optional; they enable the grounding metrics
  (`GroundingAccuracy`, `ParameterRecallAccuracy`, `DocRetrievalRate`). See
  [metrics](../../docs/components/metrics.md).
- `validated: false` only matters if you publish to the shared leaderboard. Private evals can
  ignore it.
