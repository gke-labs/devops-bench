# DevOps Bench — Task Generation Methodology

This document is the **repeatable specification** for turning a row of the
[expert task catalog](./catalog.md) into a valid `task.yaml` that the DevOps Bench
evaluator can run. Read this before authoring or generating any task. The
companion [running guide](./running.md) covers executing tasks and building a
leaderboard.

A summary an agent can follow while working in the repo lives in
[`AGENTS.md`](../../AGENTS.md); this document is the authoritative spec.

---

## 1. How the harness consumes a task

`pkg/evaluator/loader.py` walks the `tasks/` tree (recursively) and loads every
`task.yaml` it finds. Each file is parsed by `yaml.safe_load`, so **unknown keys
are ignored** — we can safely add tracking metadata (`category`, `difficulty`,
`source`, `task_class`) without breaking the loader.

The fields the loader/evaluator actually read:

| Field | Required | Purpose |
| :-- | :-- | :-- |
| `task_id` | yes | Sort key & identity. Must be globally unique (see §3). |
| `name` | yes | Human/slug name; defaults to the directory name. |
| `prompt` | yes | The instruction handed to the agent under test. |
| `expected_output` | yes | The grading rubric (see §4). |
| `infrastructure` | no | Provisioning block (see §6). |
| `chaos_spec` | no | Fault-injection spec for dynamic tasks (see §7). |
| `verification_spec` | no | Live cluster-state assertions for dynamic tasks (see §7). |
| `documentation` | no | Grounding constraints scored for citation accuracy (see §8). |
| `retrieval_context` | no | Optional RAG context list. |

## 2. Directory & naming conventions

```
tasks/<provider>/<task-slug>/task.yaml
```

- `<provider>`:
  - `generic` — cloud-agnostic Kubernetes tasks that run on any cluster (kind, GKE, EKS…).
  - `gcp` — tasks that depend on GCP/GKE-specific resources (Cloud Armor, Workload
    Identity, Filestore, BackendConfig, FrontendConfig, Binary Auth, etc.).
  - Add new provider dirs (`aws`, `azure`) only when a task is provider-specific.
- `<task-slug>` — lowercase kebab-case, derived from the catalog **Task Name**
  (e.g. `Debug CrashLoop` → `debug-crashloop`, `HPA Configuration` → `hpa-configuration`).
- Supporting fixtures (manifests, app source) live alongside `task.yaml` in the same dir.

> The top-level split is **by cloud**, not by the catalog's Dev/Platform column.
> Dev/Platform and Easy/Hard/Complex are captured as metadata fields (§5), not directories.

## 3. `task_id` allocation

`task_id` is the loader's sort and identity key. Today IDs collide across
`tasks/` and `complextasks/` (multiple `1`s and `2`s) — a latent bug. **Do not add
to the collision.**

Rule for catalog-generated tasks:

- Allocate from the reserved **1000+ block** so generated tasks never clash with
  the hand-authored tasks (currently 1–12).
- The ID is **stable and idempotent**: `task_id = 1000 + <catalog row number>`
  (1-indexed, top to bottom of [catalog.md](./catalog.md)). Re-generating a task
  yields the same ID, so reruns and leaderboard joins stay stable.
- Example: `Debug CrashLoop` is catalog row 1 → `task_id: 1001`.

## 4. `expected_output` — the grading rubric

`expected_output` is the most important field. The evaluator turns it into
DeepEval **GEval** metrics: an overall `OutcomeValidity` score, a `ToolInvocation`
score, and **one dynamic checklist metric per bullet** under `critical requirements:`.
Each bullet is graded pass/fail independently and rolled into `ChecklistScore`.

Structure every `expected_output` like this:

```yaml
expected_output: |
  critical requirements:

  - Expected Tool Call: <tool or kubectl verb the agent should invoke>
  - <one verifiable requirement per line>
  - <each line becomes its own pass/fail check — keep them atomic>

  Expected Manifest Generated: <optional golden YAML for manifest tasks>
  apiVersion: ...
  kind: ...
```

Authoring rules:

- **One requirement per bullet.** Compound bullets ("create X and bind Y") grade
  poorly — split them.
- **Make each bullet independently verifiable** from the agent's response/trace.
- Start with an `Expected Tool Call:` line naming the tool/verb expected
  (e.g. `generate_manifest`, `kubectl logs`, `kubectl get pods`). This drives the
  `ToolInvocation` metric and matches existing tasks.
- For **manifest-generation** tasks, include a golden manifest under
  `Expected Manifest Generated:` so the judge can check semantic integrity
  (ports, images, names, namespaces).
- For **investigation** tasks, the bullets should assert the *root cause* and the
  *recommended fix*, since success = "root cause identified" (there is no manifest).
- Phrase from the catalog's **Success Metric** column — that column is the ground truth.

## 5. Metadata fields (tracking)

Add these keys for traceability and leaderboard slicing. The loader ignores them.

```yaml
category: Dev            # Dev | Platform (from catalog)
difficulty: Easy         # Easy | Hard | Complex (from catalog)
task_class: investigation  # see §9
source: catalog#1        # catalog row reference
```

## 6. `infrastructure` — provisioning block

Omit this block (or set `BENCH_NO_INFRA=true`) for pure manifest-generation tasks
that need no live cluster. Use it when the task must run against real state.

```yaml
infrastructure:
  deployer: "tofu"            # tofu | gcp | kind
  stack: "prebuilt/kind"      # OpenTofu stack dir under tf/
  teardown: true              # tear down after the task
  variables: {}               # optional stack overrides
```

- `prebuilt/kind` brings up a **bare** kind cluster only — it provisions **no
  workloads/fixtures**. Investigation tasks that need a broken pod, a specific
  deployment, etc. require an additional fixture stack or pre-applied manifest
  (see §9 / the "live cluster gap" note below).
- `prebuilt/minimum` and `prebuilt/secret-rotation` are GKE/OpenTofu stacks.
- Setting `BENCH_NO_INFRA=true` swaps in the `NoOpDeployer` regardless of the block.

## 7. `chaos_spec` & `verification_spec` — dynamic tasks

For tasks that must withstand a runtime event (load spikes, pod kills) the
framework can inject a fault and assert cluster state **itself** (via kubectl),
independent of the agent. See `complextasks/optimize-scale/task.yaml` for the
canonical example. Use these only for resilience/autoscaling tasks; most catalog
rows don't need them.

## 8. `documentation` — grounding constraints

Optional. Lets the judge score whether the agent honored documented constraints
and cited the right source. Format:

```yaml
documentation:
  - doc_name: "GKE Gateway"
    url: "https://..."
    constraints:
      - text: "Redirects must use a dedicated HTTP listener"
        critical: true
```

## 9. Task classes & the live-cluster gap

Classify every task — it determines whether it can be run locally today.

| `task_class` | What the agent must do | Runs locally now? |
| :-- | :-- | :-- |
| `manifest-generation` | Emit YAML / config from the prompt | ✅ Yes — no infra, no MCP. The proven local path. |
| `investigation` | Inspect a live cluster, identify a root cause | ⚠️ Needs an MCP toolserver wired to the cluster |
| `live-action` | Apply/modify resources on a live cluster | ⚠️ Needs an MCP toolserver + provisioned cluster |
| `plan-only` | Produce a written plan/runbook (no execution) | ✅ Yes — graded as text |

**Cluster access:** the agent's *only* channel to a cluster is an **MCP server**
(`MCP_SERVER_PATH`, default the GKE MCP binary `third_party/gke-mcp/gke-mcp`). With
`BENCH_USE_MCP=false` the agent runs **tool-less** and can only produce text, so
`investigation`/`live-action` tasks then only test the plumbing + judge.

The GKE MCP server is installed via `scripts/setup_gke_mcp.sh`. Its `*_k8s_*` tools
(`get_k8s_logs`, `describe_k8s_resource`, `list_k8s_events`, `get_k8s_resource`,
`apply_k8s_manifest`, …) resolve a **kubeconfig context** named
`gke_<project>_<location>_<cluster>` (see `pkg/tools/k8s/client.go`) — they do *not*
call the GCP API to connect. So they can drive **any** cluster, including local
**kind**, if a context with that name exists in the active kubeconfig.

To run investigation/live-action tasks on kind: seed a `gke_<project>_<location>_<cluster>`
context that points at the kind cluster (matching the `PROJECT_ID`/`LOCATION`/`CLUSTER_NAME`
the harness passes), run with `BENCH_USE_MCP=true`, and apply the task's fixture
first. See [running.md §"Investigation/live-action on kind"](./running.md). Known
quirk: `get_k8s_logs --previous` fails on kind (containerd GCs previous-container
logs); current logs work and carry the root cause.

## 10. Authoring checklist

Before considering a task done:

1. ☐ Directory is `tasks/<provider>/<slug>/` and slug matches the catalog name.
2. ☐ `task_id` is from the 1000+ block, `1000 + <row#>`, and unique.
3. ☐ `prompt` matches the catalog **Sample Prompt** (placeholders templated, §11).
4. ☐ `expected_output` has atomic `critical requirements:` bullets derived from the
      **Success Metric**, leading with `Expected Tool Call:`.
5. ☐ Manifest tasks include a golden `Expected Manifest Generated:` block.
6. ☐ Metadata fields set (`category`, `difficulty`, `task_class`, `source`).
7. ☐ `infrastructure` block present iff the task needs live state.
8. ☐ **Validates**: `python3 -c "from pkg.evaluator.loader import load_from_tasks_dir; print([t['name'] for t in load_from_tasks_dir('tasks')])"` lists the task with no warning.
9. ☐ Catalog row status updated in [catalog.md](./catalog.md).

## 11. Placeholders

The evaluator substitutes these at run time (`replace_placeholders`):

- `{{GCP_PROJECT_ID}}` / `{{PROJECT_ID}}`
- `{{GKE_CLUSTER_NAME}}` / `{{CLUSTER_NAME}}`
- `{{NAMESPACE}}` (env `NAMESPACE`)
- `{{TARGET_DEPLOYMENT_NAME}}` (env `TARGET_DEPLOYMENT_NAME`)

Use them in `prompt`, `chaos_spec`, and `verification_spec` so a task is portable
across projects/clusters.
