# How to run out-of-tree tasks

You do not have to contribute a task to devops-bench to evaluate against it. A task definition
and its OpenTofu stack can live entirely in **your** repo; you point the harness at a path and
it runs. This is the recommended setup for teams whose evals are their own — private scenarios,
integrity evals, anything that shouldn't land on the shared leaderboard.

This guide covers what can live outside the repo, the three ways to handle infrastructure, the
contract an external stack must satisfy, and the four failure modes that will otherwise cost
you a run. A complete, runnable example lives in
[`examples/out-of-tree-task/`](../../examples/out-of-tree-task/).

For authoring the task spec itself — the schema, placeholders, rubric style — see
[add a task](./add-a-task.md); everything there applies unchanged. For deployers and providers,
see [infrastructure](../components/infra.md).

## What can live outside the repo

| Piece | Out-of-tree? | Mechanism |
| --- | --- | --- |
| **Task definition** | Yes | Any path passed as the CLI `source` — a directory or a single `.yaml` / `.yml` / `.json` file (`devops_bench/cli.py`, `FileSystemTaskLoader` in `devops_bench/tasks/loader.py`) |
| **OpenTofu stack** | Yes | An absolute (or `~`) `stack:` path is used as-is; only a *relative* value resolves under `<repo>/tf` (`TFDeployer.__init__`, `devops_bench/deployers/tofu.py`) |
| **Cloud provider** | Yes | Register under the `devops_bench.providers` entry-point group (`devops_bench/providers/base.py`) |
| **Verifier** | Yes | Register under the `devops_bench.verifiers` entry-point group (`devops_bench/verification/base.py`) |
| **Metric** | Yes | Register under the `devops_bench.metrics` entry-point group (`devops_bench/metrics/base.py`) |
| **Deployer** | **No** | Selected by a fixed branch in `get_deployer` (`devops_bench/deployers/factory.py`); only `tofu` and `noop` exist. Contribute one upstream if you need a third |
| **Agent harness** | **No** | The `AGENTS` registry declares no entry-point group (`devops_bench/agents/base.py`). See [add an agent harness](./add-an-agent-harness.md) |

You rarely need a new deployer. `TFDeployer` is the universal OpenTofu engine — a new target is
almost always a new *provider* plus a stack, and both of those can be yours.

## Three ways to handle infrastructure

### 1. Bring your own Terraform

Give `stack:` an absolute path. The only real constraint is that the stack must satisfy the
[output contract](#what-an-external-stack-must-provide).

```yaml
infrastructure:
  deployer: "tofu"
  provider: "gcp"        # required — see gotcha 1
  stack: "/home/me/my-evals/tf/my-stack"
  teardown: true
  variables:
    node_count: 3
```

### 2. Set infra up out of band

`deployer: noop` skips provisioning entirely. The harness creates and destroys nothing and runs
the agent against whatever your kubeconfig currently points at — an existing cluster you manage
yourself, or no cluster at all for manifest-generation tasks.

```yaml
infrastructure:
  deployer: "noop"
```

### 3. Ship a custom cloud provider

Subclass `Provider` (`devops_bench/providers/base.py`), decorate it with
`@PROVIDERS.register("<name>")`, and expose it from your own package:

```toml
# your package's pyproject.toml
[project.entry-points."devops_bench.providers"]
my-cloud = "my_package.provider:MyCloudProvider"
```

Install that package alongside devops-bench and `provider: "my-cloud"` resolves. The registry
scans the entry-point group lazily on first miss (`devops_bench/core/registry.py`), so no
change to this repo is needed. The same pattern works for verifiers and metrics.

## What an external stack must provide

> [!IMPORTANT]
> Every stack `TFDeployer` drives **must** output `cluster_name` and `cluster_location`. That's
> the contract `get_cluster_info()` reads back, and a missing or empty value is a hard
> `ConfigError`. Note the second name: `cluster_location`, not `location`.

```hcl
output "cluster_name" {
  value = kind_cluster.default.name
}

output "cluster_location" {
  value = "local"
}
```

The stack must also **declare** the variables the provider injects — `cluster_name`,
`location`, `project_id`, `infra_provider`, and `kubeconfig_path`, depending on the provider
(`resolve_variables()` in `devops_bench/providers/gcp.py` and `kind.py`). See gotcha 4.

## Gotchas

These are the four things that bite. Each is current behavior, verified against the code.

### 1. An external stack must name its provider explicitly

For in-repo stacks the provider is deduced from the stack name (`kind` in the name means kind,
otherwise gcp). That deduction is **deliberately not applied** to external stacks —
`_select_provider` (`devops_bench/deployers/factory.py`) raises rather than guess:

```
ConfigError: external stack '/home/me/my-evals/tf/my-stack' requires an explicit provider;
set 'provider' in task config or the INFRA_PROVIDER env var (e.g. 'gcp' or 'kind')
```

Set `provider:` in the `infrastructure:` block, or export `INFRA_PROVIDER`. The env var wins.

### 2. External stacks do not get per-run isolation

Under `--parallel`, in-repo stacks are copied into a private per-run working directory so
concurrent runs don't contend on `.terraform.lock.hcl` (no lock file is committed, so every
`init` rewrites it). `_isolated_work_dir` (`devops_bench/deployers/tofu.py`) **cannot relocate
an external stack safely, so it returns the original directory unchanged.**

Two concurrent runs pointing at the *same* external stack directory will therefore fight over
its lock file. If you run a matrix, give each concurrent run its own copy of the stack:

```bash
cp -r ~/my-evals/tf/my-stack /tmp/stack-$RUN_ID
# ...and point that run's task at /tmp/stack-$RUN_ID
```

Per-run OpenTofu **state** is still isolated (`TF_DATA_DIR` and the state file are keyed per
run) — it's only the working directory that's shared.

### 3. Relative module sources break outside the repo

In-repo stacks pull in shared modules with relative paths — `source = "../../modules/cluster"`
in `tf/prebuilt/minimum/main.tf`. Copy that stack elsewhere and the path no longer resolves.
Either declare your resources inline, or reference the modules over git:

```hcl
module "cluster" {
  source = "git::https://github.com/gke-labs/devops-bench.git//tf/modules/cluster?ref=main"
  # ...
}
```

### 4. Undeclared variables are silently dropped

`TFDeployer._var_flags` filters the variables it passes against the ones your stack actually
declares. A **provider-injected** variable your stack doesn't declare is dropped with a log
warning, not an error — so a stack that forgets `variable "cluster_name"` quietly provisions a
cluster named by its own default instead of the run-unique name the harness chose. Under a
parallel matrix, that means every concurrent run tries to create the *same* cluster.

Keys you set yourself in the task's `variables:` block behave differently: those are tracked as
custom keys and an undeclared one raises a `ConfigError` outright, on the theory that you
clearly meant the stack to receive it.

Declare everything the provider injects, even what your stack ignores. See
[`examples/out-of-tree-task/tf/variables.tf`](../../examples/out-of-tree-task/tf/variables.tf).

## Running it

Same CLI as any other task — the `source` is just a different path:

```bash
# no infra at all
BENCH_NO_INFRA=true python -m devops_bench --no-infra /abs/path/to/my-task.yaml

# your own stack, real provisioning
python -m devops_bench --project my-proj --cluster eval /abs/path/to/my-task.yaml

# a whole directory of your tasks
python -m devops_bench --project my-proj --cluster eval /abs/path/to/my-evals/tasks/
```

A directory source is scanned recursively for `task.yaml` files. All the usual flags apply —
see [run evals](./run-evals.md).

> [!NOTE]
> **In the matrix wrapper** (`scripts/bastion/run_matrix.sh`), `MATRIX_TASKS` takes your paths
> verbatim, so absolute out-of-tree paths work for **local** runs (each combo runs from the
> repo root). Two caveats: `MATRIX_TASKS=ALL` is repo-scoped — it enumerates
> `find tasks -name task.yaml` and will not see your tasks — and under `BENCH_REMOTE=1` the
> wrapper syncs only the devops-bench working tree to the bastion and runs from there, so an
> out-of-tree path must already exist at that same absolute path **on the bastion**. Copy your
> task repo and stack over yourself before launching a remote matrix.

## Leaderboard

Out-of-tree tasks are for **your** results, not the shared board:

- `validated: true` gates leaderboard eligibility, and validation means a human vetted the task
  in this repo. Leave it `false` for private evals.
- Task ids are not coordinated across repos. Yours may collide with an in-repo id; that's fine
  in isolation but makes shared aggregation ambiguous.

If a task turns out to be broadly useful, contribute it — run the `task-review` skill and open
a PR to `tasks/`.
