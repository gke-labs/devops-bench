# DevOps Bench — Running Tasks & Building a Leaderboard

How to run generated tasks against the framework, collect outcomes, and aggregate
them into a model leaderboard. Pairs with the
[generation methodology](./methodology.md).

---

## 1. Run modes & what they validate

| Mode | Agent tools | Infra | What it proves |
| :-- | :-- | :-- | :-- |
| **Local smoke** (gemma4:e2b, no MCP) | none | `BENCH_NO_INFRA=true` | Generation → harness → judge plumbing works; manifest tasks can pass |
| **Local + kind** | needs kind MCP (not wired yet) | kind cluster | Investigation/live-action on a free cluster |
| **Full / leaderboard** | GKE MCP | real GKE + GCP creds | Meaningful per-model scores across the catalog |

> Local smoke with `gemma4:e2b` as both agent and judge is a **pipeline check, not
> leaderboard data**. A real leaderboard needs capable agent models
> (e.g. Gemini 3 Pro, Claude Opus) + a strong judge + GCP for live-infra tasks.
> See [methodology §9](./methodology.md#9-task-classes--the-live-cluster-gap) for
> the kind/MCP gap.

## 2. Local smoke run (the working local path)

Uses Ollama `gemma4:e2b` as agent + judge, no MCP, no infra. Mirrors
`scripts/run_ollama_e2e_test.sh`.

```bash
# Ollama must be serving and have gemma4:e2b pulled:
#   ollama serve & ; ollama pull gemma4:e2b

export BENCH_AGENT_TYPE=api
export BENCH_USE_MCP=false
export BENCH_NO_INFRA=true
export AGENT_PROVIDER=ollama   JUDGE_PROVIDER=ollama
export AGENT_MODEL=gemma4:e2b  JUDGE_MODEL=gemma4:e2b
export OLLAMA_BASE_URL="http://127.0.0.1:11434/v1"
export GCP_PROJECT_ID=test-project CLUSTER_NAME=test-cluster

python3 pkg/evaluator/evaluate.py tasks/generic/debug-crashloop/task.yaml
```

To run the whole suite, point the script at the `tasks/` directory instead of a
single file (the loader walks recursively).

## 2b. Investigation / live-action on kind (GKE MCP → kind)

The GKE MCP server (`third_party/gke-mcp/gke-mcp`, built by
`scripts/setup_gke_mcp.sh`) lets the agent read/act on a cluster. Its `*_k8s_*`
tools connect via a kubeconfig context named `gke_<project>_<location>_<cluster>`,
not the GCP API — so they work against **kind** once such a context is seeded.

```bash
# 1) Seed a gke_<proj>_<loc>_<cluster> context pointing at the kind cluster,
#    matching the identifiers the harness/agent will use:
PROJ=test-project; LOC=us-central1; CLU=test-cluster
CTX="gke_${PROJ}_${LOC}_${CLU}"
kubectl config --kubeconfig ~/.kube/config_kind get-contexts   # find the kind context
# duplicate the kind context under the gke_ name (see methodology §9), then:
kubectl --context "$CTX" get nodes      # verify it reaches kind

# 2) Apply the task's fixture so there is something to inspect/act on:
kubectl --context "$CTX" apply -f tasks/generic/debug-crashloop/frontend-crashloop.yaml

# 3) Run the task WITH MCP tools:
export KUBECONFIG=~/.kube/config_kind
export BENCH_AGENT_TYPE=api BENCH_USE_MCP=true
export MCP_SERVER_PATH=third_party/gke-mcp/gke-mcp
export AGENT_PROVIDER=ollama AGENT_MODEL=gemma4:e2b
export JUDGE_PROVIDER=ollama JUDGE_MODEL=gemma4:e2b
export OLLAMA_BASE_URL="http://127.0.0.1:11434/v1"
export GCP_PROJECT_ID=$PROJ GCP_LOCATION=$LOC CLUSTER_NAME=$CLU NAMESPACE=default
python3 pkg/evaluator/evaluate.py tasks/generic/debug-crashloop/task.yaml
```

The agent must pass `project_id`/`location`/`cluster_name` to each k8s tool; ensure
the task prompt/context makes these available. Known quirk: `get_k8s_logs
--previous` fails on kind (containerd GCs previous-container logs) — current logs
work. Note: GKE-only tools (`list_clusters`, `create_cluster`, `query_logs`,
`list_recommendations`, …) still require real GCP and won't work against kind.

**Ollama context window (required for MCP runs).** The GKE MCP tool schema is large
(~6.9k tokens for all 34 tools). Ollama defaults `num_ctx` to 4096 and the
OpenAI-compatible endpoint **ignores** `extra_body.options.num_ctx`, so the tool
list gets truncated and the model returns an **empty** response with no tool calls.
Fix: bake a larger context into a derived model (applies on the OpenAI endpoint):

```bash
printf 'FROM gemma4:e2b\nPARAMETER num_ctx 32768\n' > /tmp/Modelfile.gemma4mcp
ollama create gemma4-mcp:e2b -f /tmp/Modelfile.gemma4mcp
# then set AGENT_MODEL=gemma4-mcp:e2b (JUDGE can stay gemma4:e2b)
```

Alternatively start the server with `OLLAMA_CONTEXT_LENGTH=32768 ollama serve` to
raise the default for all models. With this, gemma4:e2b drives the full 34-tool set
(verified: it calls `get_k8s_resource`/`describe_k8s_resource`/`get_k8s_logs`).
At small tool counts (5–10) the 2B model still reasons weakly; for more robust
tool-use a larger Gemma 4 (e.g. `e4b`) helps, but `e2b` works for the MCP path.

## 3. Full run (per model, for the leaderboard)

```bash
export BENCH_AGENT_TYPE=api
export BENCH_USE_MCP=true                 # GKE MCP for live tasks
export AGENT_PROVIDER=google AGENT_MODEL=gemini-3.1-pro-preview AGENT_API_KEY=...
export JUDGE_PROVIDER=google JUDGE_MODEL=gemini-3.1-pro-preview JUDGE_API_KEY=...
export GCP_PROJECT_ID=<proj> GKE_CLUSTER_NAME=<cluster>
export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/application_default_credentials.json

python3 pkg/evaluator/evaluate.py tasks/        # whole catalog
```

Swap `AGENT_PROVIDER`/`AGENT_MODEL` (e.g. `anthropic` / `claude-opus-4-8`) to add a
model to the board. **Keep the judge fixed across models** so scores are comparable.

## 4. Where results land

Each run writes `results/run_<YYYYMMDD_HHMMSS>/`:

- `results.json` — per-task inputs, agent output, trajectory, latency, tokens, and
  `scores` (OutcomeValidity, ToolInvocation, per-bullet checks, ChecklistScore).
- `generated_files/` — any artifacts the agent produced.

A task is considered **passed** when its checks report `success: true` (GEval
normalizes the judge's 0–10 to 0–1; threshold ≈ 0.5; `ChecklistScore` is
fraction of bullets passed).

## 5. Building the leaderboard

Recommended layout for comparable runs — one results dir per model:

```
results/leaderboard/<model-id>/run_.../results.json
```

Aggregation approach (to be scripted as the suite grows):

1. For each model, load every task's `ChecklistScore.score` and `OutcomeValidity`.
2. Compute per-model: tasks passed / total, mean ChecklistScore, mean latency,
   mean total tokens. Slice by `category` and `difficulty` (from task metadata).
3. Emit a markdown table:

   | Model | Pass rate | Mean checklist | Easy | Hard | Complex | Mean latency | Mean tokens |
   | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |

Keep the judge model and task set identical across rows; note both in the
leaderboard header so results stay reproducible.

## 6. Reproducibility notes

- Pin `AGENT_MODEL` / `JUDGE_MODEL` versions in the leaderboard header.
- Record the task-set git SHA (the catalog evolves).
- LLM judges are stochastic — for borderline tasks, average ≥3 runs or fix
  temperature where the provider allows.
