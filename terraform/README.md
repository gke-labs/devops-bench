# Terraform Infrastructure

This directory contains the Terraform modules and prebuilt configurations used to provision infrastructure for the benchmarks.

## Directory Structure

- `modules/`: Reusable infrastructure components (e.g., GKE cluster, Networking).
- `prebuilt/`: Standard, reusable environment configurations (e.g., `minimum` 3-node cluster).
- `tasks/`: Task-specific infrastructure definitions (not yet used, but supported).

## Usage in tasks

Tasks can specify their infrastructure requirements in their `task.yaml` file:

```yaml
infrastructure:
  deployer: "terraform"
  stack: "prebuilt/minimum"
  teardown: true
  variables:
    node_count: 3
    machine_type: "e2-standard-2"
```

## Available Prebuilt Stacks

### `minimum`
A basic GKE cluster with:
- 3 nodes
- Machine type: `e2-standard-2`
- GKE Standard cluster w/ default configuration
