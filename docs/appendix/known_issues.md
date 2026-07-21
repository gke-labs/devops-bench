# Known issues, recovery & workarounds

Failure recovery and deliberate workarounds for the refactored eval pipeline (`python -m devops_bench`, `scripts/bastion/run_matrix.sh`, `devops_bench/`). Section 1 is a recovery router: match your symptom, apply the action. Section 2 catalogues the hacks currently in the code path and what would let us remove them.

## Section 1 — Issue router (recover from eval failures)

If an eval fails, find the symptom below and apply the action. Many failures are transient infrastructure flakes — those are marked **Retry** and should simply be retried (after cleaning stale state), not debugged.

> [!TIP]
> **Class** tells you what to do without reading the row. `Infra flake — retry`: re-run the combo after the *Before any retry* cleanup; do **not** open the code. `Config / auth`: a credential or settings fix is required before it will ever pass. `Setup`: a one-time host or cloud-project prerequisite is missing.

| Symptom / error signature | Root cause | Fix / recovery action | Class |
|---|---|---|---|
| `Vertex AI API error (429): Resource exhausted` (`RESOURCE_EXHAUSTED`), agent run ends mid-trajectory | Transient Vertex per-minute quota on long, high-token agentic runs (multi-region, cp-recovery exceed 1M input tokens) | Not a model miss — **retry the combo**. If it recurs, lower `MAX_PARALLEL` or raise the Vertex quota | **Infra flake — retry** |
| GCP `409 already exists` on cluster (re)create, naming a `gke-nodes-*` service account | `gke-nodes-<cluster>` node SA is **not** random-suffixed; a failed teardown orphaned it | Delete the orphan SA (`gcloud iam service-accounts delete gke-nodes-<cluster>@<project>.iam.gserviceaccount.com`), then **retry**. Durable fix still open (see §2 H6) | **Setup** (run retries once cleaned) |
| Task fails in ~2 min at `tofu plan`: `could not locate any control plane nodes for cluster '<hash>-eval'` | A prior run's per-run state under `/tmp/devops-bench-runs/<task>__<model>__<arm>` is reused and references an already-torn-down cluster | **Wipe stale run state before re-running**: `rm -rf /tmp/devops-bench-runs/*` plus the kind/cluster cleanup in *Before any retry*, then retry | **Setup** |
| Transient SSH `exit 255` to the bastion mid-run | Relay/gcpnode/cert blip on the IAP-SSH connection | **Retry the ssh** — the *detached* run on the VM is unaffected; re-attach with `RESUME_STAMP=<stamp>` | **Infra flake — retry** |
| `ssh: connect ... Connection closed by UNKNOWN port 65535` on **every** attempt, **with a valid gcert** (`gcertstatus` OK) | Wrong/unreachable bastion host — `BASTION_VM`/`BASTION_ZONE`/`BASTION_PROJECT` don't match your actual VM (wrong name/project/zone, or the VM is stopped); the constructed gcpnode host closes with the *same* signature as an expired cert | Read the real values from the TF module (`tofu -chdir=tf/prebuilt/bastion output iap_ssh_command`) and set `BASTION_VM`/`BASTION_ZONE`/`BASTION_PROJECT` accordingly. Re-check gcert only after the host is right | **Config / auth** |
| `gemini subprocess error: ... exit code -1` | This is a **timeout, not a crash** — `core.subprocess.run` returns `-1` on `TimeoutExpired` (usually an MCP approval hang) | Fix the *hang* (set `--approval-mode yolo` + folder trust below) rather than just raising `AGENT_TIMEOUT_SEC`; only raise the timeout after | **Config / auth** |
| gemini `mcp list` shows server `Disabled`; model writes its own MCP client; or run hangs to timeout with MCP configured (`--skip-trust` alone insufficient) | Untrusted per-run cwd suppresses MCP, **and** with no approval mode MCP calls block on interactive confirmation | Needs **both**: set `security.folderTrust.enabled=false` in user-level `~/.gemini/settings.json`, **and** pass `--approval-mode yolo` in argv | **Config / auth** |
| oc on Vertex: `No API key found for provider "google-vertex"` under parallel runs | The ADC marker lives only in the global sqlite auth store; an isolated `OPENCLAW_STATE_DIR` can't see it | Export `GOOGLE_CLOUD_API_KEY=gcp-vertex-credentials` (the portable env marker — this is exactly what `BENCH_VERTEX=1` does) | **Config / auth** |
| oc on Vertex: `401 Incorrect API key` (request sent to `platform.openai.com`) | The per-run provider entry **replaces** the built-in one and is missing the Vertex transport, so oc falls back to the OpenAI transport | Run on current code — the harness writes a per-run `openclaw.json` that pins `"api": "google-vertex"` (+ `"baseUrl"`) for the Vertex transport; combine with the `BENCH_VERTEX=1` ADC marker above. If seen, you are on stale code — sync/reinstall | **Config / auth** |
| Vertex `404 Publisher model ... not found`; judge silently fails / 404s | Wrong location or non-`-preview` model id — `gemini-3.x` previews 404 on regional endpoints | Use the **`global`** location (`GOOGLE_CLOUD_LOCATION=global` / `GCP_VERTEX_LOCATION=global`) and a `-preview` model id; the judge default needs `JUDGE_MODEL=gemini-3.1-pro-preview` | **Config / auth** |
| GKE task: `Error 403: <API> has not been used in project … or it is disabled` (e.g. `sqladmin`, `servicenetworking`) | A required GCP API isn't enabled in the eval project | `gcloud services enable <api>.googleapis.com`, wait a few min to propagate, then retry (Cloud SQL → `sqladmin`; Parallelstore/Lustre peering → `servicenetworking`) | **Setup** |
| Multi-node kind task fails: `failed to join node with kubeadm … exit status 1` | Host `fs.inotify.max_user_instances` (default 128) exhausted by a multi-node cluster (e.g. cp-recovery's HA control plane) | `sudo sysctl -w fs.inotify.max_user_instances=1280 fs.inotify.max_user_watches=1048576` (persist in `/etc/sysctl.d/`), then retry | **Setup** |
| kind task fails instantly: `docker: executable file not found in $PATH` | Docker not installed / socket missing on the bastion (kind tasks run on the host) | Install `docker.io`, start the daemon, grant the runner socket access (`setfacl -m u:$USER:rw /var/run/docker.sock`, or the `docker` group + fresh login) | **Setup** |
| Chaos `generate_load` injects nothing; HPA never scales (load is a silent no-op) | `fortio` not on `PATH` (it is installed at provision time, not baked into the image) | Install `fortio` to `~/bin` (see `scripts/bastion/vm-setup.sh`), then retry | **Setup** |
| Bastion standalone test sees **stale code** (e.g. a flag still showing its pre-fix value) | The bastion venv has an *installed* `devops_bench`; `python3 /tmp/x.py` imports the package, not the synced source | Run with `PYTHONPATH=$HOME/devops-bench`, or `python -m devops_bench` from the source dir (what the matrix already does) | **Setup** |
| **All trajectories empty** (`trajectory: []`, `tools: []`), `ToolInvocation` 0.0, scores ~½ of the legacy arm — though the agent clearly acted; run log shows `oc sessions exited 127: /usr/bin/env: 'node': No such file or directory` | The refactored arm's `oc sessions` / `export-trajectory` extraction runs `oc` as a **direct argv subprocess** (no nvm sourced), so on an nvm-managed host Node isn't on `PATH` → exit 127 → trajectory **silently emptied** → every tool/checklist check fails | Put Node on the runner `PATH` (`ln -s "$(command -v node)" ~/bin/node`; `~/bin` is on the runner PATH). Current code also prepends the nvm Node dir for these calls (`_ensure_node_on_path` in `agents/cli/openclaw/agent.py`); if seen, sync/reinstall | **Config / setup** |

After applying a fix, retry the run. For any infra-flake row, run the cleanup below first.

### Before any retry

> [!IMPORTANT]
> Stale run state and orphaned cloud resources are the most common cause of a "fresh" matrix failing instantly. Clean them before every (re)launch.

On the bastion:

```bash
# 1. Wipe stale per-run scratch + state (fixes "could not locate any control plane nodes")
rm -rf /tmp/devops-bench-runs/*

# 2. Delete leftover kind clusters and orphaned -eval containers (kind get clusters
#    does not track leaked node containers)
for c in $(kind get clusters); do kind delete cluster --name "$c"; done
docker rm -f $(docker ps -aq --filter name=-eval) 2>/dev/null || true

# 3. Kill stale runner / harness / agent processes from a prior launch
pkill -f matrix-runner ; pkill -f devops_bench ; pkill -f 'oc agent' 2>/dev/null || true
```

Then delete orphaned cloud resources left by a failed teardown:

- **Clusters** — any `<hash>-eval` GKE clusters from a crashed run.
- **`gke-nodes-*` service accounts** — the deterministic node-SA name causes `409 already exists` on re-run until deleted.
- **Task-specific leftovers** — e.g. leaked `hello-app-*` Artifact Registry repos, Cloud SQL instances (note the ~1-week name tombstone), and orphan auto-mode VPCs (`lus-net-*` / `ps-net-*`).

## Section 2 — Known hacks & workarounds

Deliberate workarounds currently in the refactored code path. Each notes what it does and what would let us remove it.

| What | Where (file / area) | Why | Removal condition |
|---|---|---|---|
| **Per-run tofu isolation** copies the whole `tf/` tree into `<run_dir>/tf/` and writes state to `<run_dir>/terraform.tfstate` | `devops_bench/deployers/tofu.py` (`_isolated_work_dir`); `devops_bench/core/run_env.py` (`TF_DATA_DIR`) | Stacks use relative module sources, and concurrent runs would otherwise contend on a shared `.terraform.lock.hcl` + state in `tf/prebuilt/<stack>` | Module sources made run-relocatable without a full-tree copy (this is the principled isolation fix, not pure debt — low priority) |
| **`GOOGLE_CLOUD_API_KEY=gcp-vertex-credentials` ADC marker** exported for oc on Vertex | `scripts/bastion/_matrix_lib.sh` (set when `BENCH_VERTEX`); oc env resolver | An isolated `OPENCLAW_STATE_DIR` can't read the ADC marker that otherwise lives only in the global sqlite auth store; the literal marker tells oc's `google-vertex` transport to use ADC | oc resolves Vertex ADC without a per-run sqlite marker (env-based resolver already in place; remove when the global store dependency is gone) |
| **Stale-state manual pre-flight wipe** (`rm -rf /tmp/devops-bench-runs/*` + kind/container cleanup) | Operator step / run skills (`RESUME_STAMP` opt-in to reuse) | The per-run state dir is keyed deterministically by `task__model__arm`; a prior run's state references a deleted cluster and is reused, failing at `tofu plan` | `RunEnv` (or a `devops-bench clean` subcommand) self-detects dangling state and re-inits instead of relying on a human `rm -rf` |
| **Deterministic node-SA name** `gke-nodes-<cluster>` (no random suffix) | `tf/prebuilt/*/main.tf` | Cluster GCP names are run-scoped, but the node SA name is not suffixed; a failed teardown orphans it → `409 already exists` on re-run. Multi-cluster stacks truncate to `substr(cluster_name,0,15)`, collapsing east/west SAs to one id | Add a `random_id` suffix (or `create_ignore_already_exists`) to the node SA, carry the discriminator in the first 15 chars, and always sweep `gke-nodes-*` on teardown — multi-cluster GKE tasks are not parallel-safe until this lands |
| **Chaos port-forward fallback** (resolve the workload's external LoadBalancer URL first; fall back to `kubectl port-forward` on timeout) | `devops_bench/chaos/faults/generate_load.py`; `devops_bench/evalharness/scenario.py` | The bastion can't route to a cluster-internal IP, and a port-forward races a not-yet-Ready pod (exits code 1) when the agent mutates the deployment | Make the LB-vs-PF decision explicit in the chaos report and **hard-fail** when neither transport reaches the workload, so a no-op load is loud (it is currently silent if both fail) |
| **Kyverno/OPA admission-webhook retry loop** (bounded retry on policy apply) | `tf/prebuilt/opa-remediation-kind/scripts/setup.sh` | The Kyverno webhook can take seconds to start serving after the deployment is Available; applying too early fails with `context deadline exceeded` | Poll the `Validating`/`MutatingWebhookConfiguration` (or the service endpoint) readiness instead of a fixed-attempt sleep loop |
| **Leaked Artifact Registry sweep** (destroy-time `null_resource` shelling out to `gcloud artifacts repositories delete`) | `tf/prebuilt/minimum/main.tf` | `deploy-hello-app` creates a project-global `hello-app-<cluster>` AR repo the stack doesn't own, so normal `tofu destroy` wouldn't remove it | Have the stack own the repo as a managed `google_artifact_registry_repository`, or target a pre-provisioned repo, so teardown is not a best-effort shell-out |
| **Off-cluster `external_http_probe` grades internet exposure (deploy-hello-app)** | `tasks/gcp/deploy-hello-app/task.yaml` | The `serving-http` objective now GETs the Service's external LoadBalancer address from the verifier host (off-cluster), so a 200 proves both HTTP serving and internet reachability, mechanism-agnostic across LoadBalancer Service or Ingress | Needs the verifier host to have network egress to the LB's external address, and carries several residual limitations documented in the verifier docstring (backend identity, multi-match selector, https TLS not verified, Gateway API discovery) |
| **Runtime `fortio` install** at provision time (network download into `~/bin`) | `scripts/bastion/vm-setup.sh` | The chaos `generate_load` fault shells out to `fortio`; without it on `PATH` the load spike is a silent no-op | Bake `fortio` (and `docker.io`, the inotify sysctls) into the bastion image, or have the chaos fault hard-fail at startup if `fortio` is missing |
| **MCP tool-name normalization** strips the `<server>__` prefix before matching | `devops_bench/metrics/pipeline.py` (`_canonical_tool_name`) | MCP tools surface as `<server>__<tool>`; without stripping, `bash` vs `default__bash` scored 0 on tool-invocation | Strip the prefix only against the *known* set of configured MCP server names (from the agent config / `capabilities_granted`), not a blind `split("__")` that would also truncate a legit `my__tool` |
| **KUBECONFIG explicitly passed to MCP server processes** (per-agent, per-spawn) | `devops_bench/agents/cli/openclaw/agent.py` | `RunEnv` sets `KUBECONFIG` in process env, but MCP server spawn didn't inherit it, so MCP servers used the ambient `~/.kube/config` and mixed cluster targets under parallelism | Centralize MCP-server-environment construction in one shared `agents/` helper that always derives env from `RunEnv`, so a new agent can't silently regress to ambient config |
| **`generation_only` derived from `deployer == "noop"`** to skip `OutcomeValidity` | `devops_bench/evalharness/default.py`; `devops_bench/metrics/pipeline.py` | Manifest-only (noop) tasks never apply to a cluster, so they would score 0 on `OutcomeValidity`; the metric layer infers "generation-only" from the deployer string | Make `generation_only` an explicit (or explicitly-derivable) `Task` field so a non-noop generation-only task isn't mis-judged and the metric layer needn't know deployer names |
| **`validated` flag defaults `false`** (gates leaderboard promotion only) | `devops_bench/tasks/schema.py`; `devops_bench/results/row.py`, `normalize.py` | Keeps unvetted tasks off the leaderboard until a human sets `validated: true` | The flag gates promotion but **not running** — an unvetted task still burns quota. Add a CI `validate-task` pass (schema + spec parse + unique id) and a `--require-validated` run mode |
| **Swallowed scoring / per-metric errors** (broad `except Exception` so an already-written `results.json` survives a judge crash) | `devops_bench/evalharness/default.py`; `devops_bench/metrics/pipeline.py` | A judge/GEval crash must not discard an already-completed execution record (raw `results.json` is written before scoring) | Keep the isolation but record a typed scoring-error sentinel in `scores` and surface a distinct exit/manifest flag, so unscored runs are visibly degraded rather than silently empty |

> [!NOTE]
> **Observability caveat.** `results.json` carries no token fields (tokens live only in `rows.json` / `manifest.json`), and a run that times out is killed before `oc sessions export-trajectory` runs, so the heaviest runs can persist `tokens: {}`. Treat token/cost figures as the clean-completion subset only until a durable per-turn token checkpoint lands.

---

See also: [Running evals](../how-to/run-evals.md) for the full run workflow, and [Bastion](../components/bastion.md) for host setup and capabilities wiring.
