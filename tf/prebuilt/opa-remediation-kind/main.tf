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
      REPO_PATH     = pathexpand(var.repo_path)
      MANIFESTS_DIR = "${path.module}/manifests"
    }
  }
}
