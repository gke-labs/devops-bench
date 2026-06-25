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

# Single-node kind cluster on the bastion host. cluster_name is run-token-prefixed
# by the harness, so concurrent runs get distinct Docker containers/nodes.
resource "kind_cluster" "default" {
  name            = var.cluster_name
  node_image      = var.node_image
  kubeconfig_path = pathexpand(var.kubeconfig_path)
  wait_for_ready  = true
}

# Apply the broken 'frontend' fixture so the agent has a real CrashLoopBackOff to
# investigate. Runs during `tofu apply`, before the agent starts. (prebuilt/kind
# brings up a bare cluster only, which left this task unsolvable — see setup.sh.)
resource "null_resource" "fixture" {
  triggers = {
    cluster = kind_cluster.default.name
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = "${path.module}/scripts/setup.sh"
    environment = {
      KUBECONFIG    = pathexpand(var.kubeconfig_path)
      NAMESPACE     = var.namespace
      MANIFESTS_DIR = "${path.module}/manifests"
    }
  }
}
