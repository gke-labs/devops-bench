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
  # Addresses Pradeep's PR #64 review: seed-repo.sh rm -rf's + recreates this bare
  # repo, so a fixed path is "effectively a global resource and will break parallel
  # runs". cluster_name is run-token-prefixed, making this per-run unique on the
  # shared bastion host. The task prompt references the same path via the
  # {{CLUSTER_NAME}} placeholder. An explicit var.repo_path override still wins.
  repo_path = var.repo_path != "" ? var.repo_path : "~/migration-repo-${var.cluster_name}.git"
}

# The "production" cluster, provisioned at the START version. The agent migrates
# the deprecated manifests, validates them on a throwaway target-version kind
# cluster it creates itself, then brings this cluster to the target version.
resource "kind_cluster" "default" {
  name            = var.cluster_name
  node_image      = var.node_image
  kubeconfig_path = pathexpand(var.kubeconfig_path)
  wait_for_ready  = true
}

# Seed the manifests git repo the agent clones. Shared script + manifests live in
# the GKE stack dir so both substrates use a single source of truth.
resource "null_resource" "seed_repo" {
  triggers = {
    cluster = kind_cluster.default.name
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = "${path.module}/../migration-and-upgrade/scripts/seed-repo.sh"
    environment = {
      REPO_PATH     = pathexpand(local.repo_path)
      MANIFESTS_DIR = "${path.module}/../migration-and-upgrade/manifests"
    }
  }
}
