# OpenTofu/Terraform Infrastructure

This directory contains the OpenTofu modules and prebuilt configurations used to provision infrastructure for the benchmarks.

---

## 1. Directory Structure

- `modules/`: Reusable infrastructure components.
  - **`cluster/`**: The provider-neutral cluster router. It conditionally delegates to:
    - `cluster/gke/`: Google Kubernetes Engine (GCP) implementation.
    - `cluster/kind/`: Local Kubernetes in Docker (KinD) implementation.
- `prebuilt/`: Standard, reusable environment configurations.
  - `minimum/`: A basic cluster (GKE or KinD).
  - `gpu-stress-test/`: A cluster configured with GPU node pools.
  - Specialized stacks (e.g., `secret-rotation`, `cp-recovery-kind`) that are locked to specific providers.

---

## 2. The Provider-Neutral Cluster Abstraction

To avoid duplicating stacks for different cloud or local environments, tasks call the unified **`cluster`** module. The target environment is determined at runtime by the `cloud_provider` variable.

### Inputs for `modules/cluster`

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `cloud_provider` | `string` | **Required** | Target provider (`"gcp"` or `"kind"`) |
| `cluster_name` | `string` | **Required** | Name of the cluster |
| `location` | `string` | `""` | Region/zone (GCP) or `"local"` (KinD) |
| `node_count` | `number` | `3` | Number of worker nodes |
| `machine_type` | `string` | `""` | VM instance type (e.g., `e2-standard-2`, `g2-standard-4`) |
| `gpu_type` | `string` | `""` | Abstract GPU type (`"l4"`, `"a100"`, `"t4"`, or `""` for no GPU) |
| `gpu_count` | `number` | `1` | Number of GPUs per node (if `gpu_type` is set) |
| `project_id` | `string` | `""` | GCP Project ID (GCP-only) |
| `kubeconfig_path` | `string` | `"~/.kube/config"` | Local kubeconfig path (KinD-only) |

---

## 3. How to Run Stacks on Different Providers

When executing a task via the `devopsbench` runner, you can specify the target provider using the `--provider` flag. The runner will automatically inject the correct `cloud_provider` variable.

### Running on GCP (GKE)
```bash
devopsbench run create-deployment --provider gcp
```

### Running Locally (KinD)
```bash
devopsbench run create-deployment --provider kind
```

---

## 4. Writing a New Task

When defining a task in `task.yaml`, write it using the provider-neutral prebuilt stacks:

```yaml
# tasks/gcp/my-task/task.yaml
name: "my-generic-task"
infrastructure:
  deployer: "tofu"
  stack: "prebuilt/minimum"
  teardown: true
  variables:
    node_count: 3
    machine_type: "e2-standard-2"
```
This task can now be executed on any supported cloud or local provider without modification.
