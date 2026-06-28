# optimize-scale

Tests whether the agent can right-size and autoscale a deployment that is
**deliberately under-provisioned**, then survive a load spike.

## Fixture (`tf/prebuilt/optimize-scale`, GKE)
Each run gets its own GKE cluster (collision-free under parallel runs) pre-seeded with:
- a Deployment **and** Service named `${target_deployment_name}` (default `scale-target`),
  in `${namespace}` (default `default`),
- **1 replica, NO resource requests/limits, NO HPA** — this is the work the agent must do,
- a CPU-burning HTTP server listening on **port 8080** (see port note below).

The integration contract (`TARGET_DEPLOYMENT_NAME` / `NAMESPACE`) is pinned for both arms
by `scripts/bastion/_matrix_lib.sh` (`task_extra_env`) so the prompt, chaos `service_url`,
and verification placeholders all resolve to the seeded objects.

## Chaos + verification
After the agent works, the chaos harness injects a **load spike** (`generate_load`, qps 300)
and verification checks `pod_healthy` + `scaling_complete` (≥2 replicas).

- **The workload must listen on port 8080.** The chaos harness port-forwards
  `deployment/${target_deployment_name}` to a **fixed remote port 8080**
  (`devops_bench/chaos/faults/generate_load.py`, `_LOCAL_PORT` passed as `remote_port`).
  A workload on any other port (e.g. `registry.k8s.io/hpa-example`, which serves :80) means
  the spike never reaches the app — the run can still "pass" because the agent's HPA
  `minReplicas` scales it independent of load, but the load test is a no-op. The seeded
  workload therefore serves on 8080.
- **`fortio` must be on the bastion PATH.** The chaos agent shells out to `fortio` to
  generate the spike; `scripts/bastion/vm-setup.sh` installs it. Without it the spike no-ops.

## Expected agent actions (scored)
1. Add resource requests/limits to the deployment.
2. Create an HPA with `minReplicas > 1` and an appropriate target CPU.
3. Detect and handle the load spike.

## Rerunning
The per-run tofu state is keyed by `task__model__arm`; clear stale state before a rerun:
`rm -rf /tmp/devops-bench-runs/optimize-scale__*` (and delete any leftover cluster) — see the
`run-parallel-evals` skill, Phase 3.
