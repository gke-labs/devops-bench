terraform {
  required_providers {
    kind = {
      source  = "tehcyx/kind"
      version = ">= 0.5.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0.0"
    }
  }
}

provider "kind" {}

locals {
  # GitOps repo path on the shared bastion host. setup.sh rm -rf's + reseeds it,
  # so a fixed path would let one run wipe a concurrent run's repo. cluster_name
  # is run-token-prefixed, making this per-run unique. The task prompt references
  # the same path via the {{CLUSTER_NAME}} placeholder. An explicit override wins.
  repo_path = var.repo_path != "" ? var.repo_path : "~/opa-repo-${var.cluster_name}.git"
}

# Single-node kind cluster (control-plane is schedulable on single-node kind, so
# the team workloads run here). Kyverno + the workloads are installed by setup.sh.
resource "kind_cluster" "default" {
  name            = var.cluster_name
  node_image      = var.node_image
  kubeconfig_path = pathexpand(var.kubeconfig_path)
  wait_for_ready  = true
}

# Outside-the-cluster setup: install Kyverno, apply audit policies, deploy the
# violating workloads, and seed the GitOps repo. Runs during `tofu apply`,
# before the agent starts.
resource "null_resource" "setup" {
  triggers = {
    cluster = kind_cluster.default.name
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = "${path.module}/scripts/setup.sh"
    environment = {
      KUBECONFIG    = pathexpand(var.kubeconfig_path)
      REPO_PATH     = pathexpand(local.repo_path)
      MANIFESTS_DIR = "${path.module}/manifests"
    }
  }
}
