# The Bastion

The **bastion** is an alternate execution environment for the eval harness — a static Google Compute Engine VM where infrastructure provisioning, the agent run, and the judge all happen together on one machine. It's an alternative to running the harness on your own workstation. (`bench-bastion` is the name used throughout this guide; the name is configurable.)

## What it is & why

Real GKE and local kind evals need one machine that co-locates three things:

- **Infra provisioning** — the harness runs OpenTofu to stand up (and tear down) a cluster.
- **The agent run** — the `openclaw` agent is local-only. The harness drives it as a local subprocess, so the agent has to live on the same host.
- **The judge** — grading runs right after the agent, against the same cluster.

The bastion gives you that host. It comes pre-loaded with the full toolchain and is already authenticated to GCP, so you SSH in and run evals without setting up a workstation by hand. It is generic and reusable across evals — nothing about it is tied to a single task.

## Architecture

```
   you ──SSH (IAP)──▶  bench-bastion VM
                       │  runs as: openclaw-vm-sa  (ADC via metadata server)
                       │
                       ├─ tofu apply ──▶ GKE cluster (or local kind)
                       ├─ run agent  ──▶ openclaw drives kubectl / gcloud as the VM SA
                       ├─ judge       ─▶ grade against the cluster
                       └─ tofu destroy ▶ tear it all down
```

You SSH into the VM over IAP. The VM runs as a dedicated service account, `openclaw-vm-sa`, and authenticates with **Application Default Credentials pulled from the metadata server** — there are no key files on disk. When the agent's `kubectl` or `gcloud` make calls, they act as the VM's service account through that same ADC.

> [!WARNING]
> The VM service account holds broad, owner-equivalent provisioning roles so the harness can create and destroy clusters, secrets, and IAM bindings. Use sandbox or non-production projects only.

### Access

SSH ingress is locked to **Google's IAP TCP-forwarding range** (`35.235.240.0/20`), scoped to the VM's network tag. You reach the VM by tunnelling through IAP.

Per repo convention, on Google corp hosts SSH to the **gcpnode FQDN** rather than `gcloud compute ssh`. The full command is:

```bash
ssh <user>_google_com@nic0.<vm>.<zone>.c.<project>.internal.gcpnode.com
```

So for the default `bench-bastion` in `us-central1-a` of project `my-proj`, user `jane`:

```bash
ssh jane_google_com@nic0.bench-bastion.us-central1-a.c.my-proj.internal.gcpnode.com
```

Because eval workflows open many short-lived SSH/SCP connections (syncing code, polling a run, pulling results), set up **connection multiplexing** so they all reuse one tunnel instead of re-handshaking every time. Add a host entry to `~/.ssh/config`:

```ssh-config
Host bench-bastion
    HostName nic0.bench-bastion.us-central1-a.c.my-proj.internal.gcpnode.com
    User jane_google_com
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 10m
```

Then connect with just `ssh bench-bastion`. The first connection opens a master socket; subsequent `ssh`/`scp` to the same host reuse it for up to 10 minutes of idle time (`ControlPersist`), which makes the matrix runner's repeated calls fast and avoids hammering the IAP relay.

> [!TIP]
> If you aren't on a gcpnode-enabled host, `gcloud compute ssh <vm> --zone <zone> --tunnel-through-iap` works too — the `iap_ssh_command` Terraform output gives you a ready-to-run version.

## How it's set up

Two Terraform pieces under `tf/` define the bastion:

| Path | Role |
| --- | --- |
| `tf/modules/bastion/` | Reusable module: the service account + IAM, the VM, the IAP-SSH firewall rule, and a first-boot `startup.sh` that installs the toolchain. |
| `tf/prebuilt/bastion/` | The concrete stack you apply. It grants the broad service-account roles the eval stacks need. |

The first-boot `startup.sh` installs, system-wide: OpenTofu, Node.js 22+, the Google Cloud CLI with `gke-gcloud-auth-plugin` and `kubectl`, `openclaw` (linked on `PATH` as `oc`), and `gke-mcp`.

Provision it:

```bash
cd tf/prebuilt/bastion
tofu init
tofu apply -var project_id=<your-project>
```

Outputs include `iap_ssh_command` (a ready-to-run IAP SSH command) and `sa_email` (the VM's service-account address).

Key variables and their defaults:

| Variable | Default | Notes |
| --- | --- | --- |
| `project_id` | _(required)_ | GCP project the bastion lives in. |
| `name` | `bench-bastion` | VM name; also names its firewall rule and network tag. |
| `zone` | `us-central1-a` | GCE zone. |
| `machine_type` | `e2-standard-4` | Headroom for tofu + node + the harness. |
| `image` | `ubuntu-os-cloud/ubuntu-2404-lts-amd64` | Ubuntu 24.04 LTS (ships Python 3.12). |

## Per-user setup on the VM

Once the VM is provisioned, finish the user-scoped pieces once:

```bash
~/devops-bench/scripts/bastion/vm-setup.sh
```

This uses `uv` (installed system-wide by the VM startup script) to create a `.venv` and install the harness from the lockfile (`uv sync --frozen --extra all`), and writes a `~/bench.env` template.

Then fill in `~/bench.env` — at minimum your **project** and the **judge key** — and load it:

```bash
source ~/bench.env
```

> [!NOTE]
> Per-run capabilities (the MCP server, agent skills, and the model/provider) are wired by the harness through environment variables at run time. You don't pre-configure them globally — leave that to the run.

## Pointing an eval at the bastion

SSH in, activate the environment, and run a task:

```bash
cd ~/devops-bench
source .venv/bin/activate
source ~/bench.env

# A single task:
devops-bench tasks/gcp/secret-rotation/task.yaml
```

`devops-bench` is the console script the package installs; `python -m devops_bench tasks/gcp/secret-rotation/task.yaml` runs the exact same entrypoint if you prefer the module form.

To drive a full matrix, use the matrix runner:

```bash
scripts/bastion/run_matrix.sh
```

Set `BENCH_REMOTE=1` to sync from your laptop and run on the bastion over SSH.

For the full running workflow — matrix axes, monitoring, and result handling — see [Running evals](../how-to/run-evals.md). For failure modes and gotchas, see [Known issues](../appendix/known_issues.md).
