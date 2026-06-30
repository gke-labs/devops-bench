# Running evals — shared run mechanics

The single home for the run mechanics that `run-eval`, `validate-eval`, and
`run-parallel-evals` all reuse: where to run, how to authenticate, how to come up
clean, how to launch detached, the matrix knobs, and where results land. The
skills link here instead of repeating it.

This reference is **agent-agnostic** — it describes capabilities, not specific
tools. For the per-agent mapping (sub-agents, background runs, timers, durable
state, worktrees, asking the operator) see
[`harness-capabilities.md`](./harness-capabilities.md).

For the full narrative guide see [`../../docs/how-to/run-evals.md`]; for the
failure router see [`../../docs/appendix/known_issues.md`] — this file does not
duplicate either.

---

## Choosing where to run

The matrix runs on the **runner host** — the machine where you invoke the
wrapper. **Local is the default** (`nohup` on this host, no ssh/sync, outputs in
`~/matrix-runs/<stamp>`). Set **`BENCH_REMOTE=1`** to sync the working tree to the
**bastion** and run there over ssh, pulling results back. The snippets below show
the bare command; in remote mode they run under the wrapper's ssh transport, so
the same paths (`~/secrets.env`, `~/matrix-runs/<stamp>`) just live on the VM.

**Bastion connection env (remote mode only):**

```bash
export BASTION_USE_GCPNODE=1 BASTION_VM=<your-vm> \
       BASTION_ZONE=us-central1-a BASTION_PROJECT=<proj> GCP_PROJECT_ID=<proj>
```

> [!IMPORTANT]
> **Get the bastion's identity from Terraform — don't assume the default.** The
> bastion is a TF module; read its real name/zone/project from the state instead
> of guessing: `tofu -chdir=tf/prebuilt/bastion output iap_ssh_command` prints the
> `gcloud compute ssh <name> --zone <zone> --project <project>` form. Set
> `BASTION_VM`/`BASTION_ZONE`/`BASTION_PROJECT` from that. A wrong/stopped host
> closes with `Connection closed by UNKNOWN port 65535` — the same symptom as an
> expired gcert, so verify the host before blaming creds. Use
> `REMOTE_DIR=devops-bench-<label>` to avoid clobbering another session's checkout.

---

## Authentication

Pick one mode (recommend **Vertex/ADC** — no key handling, and the only mode that
stays portable across the isolated per-run state dirs parallel runs create):

- **Vertex / ADC** — set `BENCH_VERTEX=1` and **no API keys**. Agents and judges
  use the VM service account's ADC. The runner unsets every API key and points
  everything at Vertex (location `global`).
- **API keys** — the runner sources `~/secrets.env` on the runner host, which
  must export `AGENT_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, and
  `JUDGE_API_KEY`. Check names only — **never print key values**; ask the operator
  for a missing key rather than guessing.

The **judge** always needs `JUDGE_PROVIDER` and `JUDGE_MODEL`. The default
`gemini-3.1-pro` **404s on Vertex** — always set
`JUDGE_MODEL=gemini-3.1-pro-preview` (and `AGENT_PROVIDER=google-vertex` for the
legacy oc arm).

---

## Clean-environment pre-flight

Stale per-run state and orphaned cloud resources are the most common cause of a
"fresh" run failing instantly. Before **every** launch or retry, work the
**"Before any retry" checklist** in
[`../../docs/appendix/known_issues.md`] — don't re-derive it here.

For orphaned **cloud** resources (clusters, `gke-nodes-*` service accounts,
leaked secrets / Artifact Registry repos), use the `cleanup-orphaned-resources`
skill rather than re-listing them inline.

The **local wipe** that the checklist covers, in brief:

```bash
rm -rf /tmp/devops-bench-runs/*                              # stale per-run state
for c in $(kind get clusters); do kind delete cluster --name "$c"; done
pkill -f matrix-runner ; pkill -f devops_bench ; pkill -f 'oc agent' 2>/dev/null || true
```

---

## Launching (detached)

`scripts/bastion/run_matrix.sh` (refactored arm) and `run_matrix_legacy.sh`
(legacy/oc arm) both run the matrix **detached under `nohup`**, poll for a
`~/matrix-runs/<stamp>/.done` marker, and pull results. They print a `STAMP` on
launch — record `RESUME_STAMP=<stamp>` in durable state; it is your handle for
monitoring, retry, and re-attach. If your poller dies the detached run keeps
going — re-attach with `RESUME_STAMP=<stamp>` and the same command.

**Always `DRY_RUN=1` first** — it prints the expanded matrix + per-combo env
without provisioning, so a typo in `MATRIX_MODELS` costs nothing instead of
clusters. At ~25–40 min/combo for infra-bearing tasks, this is the cheapest check
you have.

Example (Vertex, refactored arm; prefix `BENCH_REMOTE=1` + `BASTION_*` for remote):

```bash
BENCH_VERTEX=1 AGENT_PROVIDER=google-vertex \
JUDGE_PROVIDER=google JUDGE_MODEL=gemini-3.1-pro-preview \
MAX_PARALLEL=3 MATRIX_TASKS="tasks/gcp/secret-rotation/task.yaml" \
MATRIX_MODELS="gemini-3.1-pro-preview gemini-3.5-flash" \
MATRIX_AGENT_CONFIGS="gcli+mcp+skills oc+mcp+skills" \
RESULTS_DIR="results/<label>" \
  scripts/bastion/run_matrix.sh
```

To run **both arms in parallel**: sync once, then start each wrapper with
`SKIP_SYNC=1`, staggered a few seconds so their second-resolution `STAMP`s differ.

---

## Matrix knobs

| Variable | Meaning |
|---|---|
| `MATRIX_TASKS` | Space-separated `task.yaml` paths, or `ALL` to enumerate every task. |
| `MATRIX_MODELS` | Space-separated model ids. |
| `MATRIX_AGENT_CONFIGS` | Refactored arm only. Each `oc\|gcli` `[+mcp][+skills]` (e.g. `gcli+mcp+skills`). |
| `MAX_PARALLEL` | Max combos running at once (default `3`). Each combo is its own cluster — mind quota. |
| `AGENT_TIMEOUT_SEC` | Per-agent timeout (default `1200` in the matrix). |
| `BENCH_VERTEX` | Run agents + judges on Vertex via VM-SA ADC (no API keys). |
| `BENCH_REMOTE` | Run on the bastion over ssh; unset runs every combo locally. |
| `SKIP_SYNC` | Skip the working-tree sync to the bastion (after one real sync). |
| `BASTION_VM` | Your bastion VM name (defaults to the Terraform default `bench-bastion` — override if your VM differs). Used to build the gcpnode ssh host. |
| `BASTION_SSH_HOST` | Explicit ssh host, bypassing the `BASTION_VM`-derived name — set this to a working ssh alias's hostname. |
| `REMOTE_DIR` | Checkout dir on the VM (default `devops-bench`). Set a per-run value to avoid clobbering another session's checkout. |
| `RESULTS_DIR` | Where pulled results land (default `results/matrix`). |
| `DRY_RUN` | Print the expanded matrix + per-combo env without provisioning. |
| `RESUME_STAMP` | Skip launching; re-poll + pull an existing run by its stamp. |

---

## Where results land

Per combo on the runner host: `~/matrix-runs/<stamp>/<rid>/` with `status`
(`exit=<rc>` once finished), `run.log`, and `run_<ts>_<rid>/results.json` (the
judged per-criterion scores). A bare CLI run instead writes a single
`results/run_<ts>[_<rid>]/` (`results.json`, `rows.json`, `manifest.json`).

For how scoring works and how to read it, see
[`../../docs/components/metrics.md`].
