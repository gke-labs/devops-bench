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
  # Two run-scoped kind clusters. cluster-1 IS the harness-supplied
  # (run-token-prefixed) cluster_name — the client/primary returned to the harness
  # and addressable in the prompt as {{CLUSTER_NAME}}. cluster-2 appends "-peer"
  # ({{CLUSTER_NAME}}-peer) and hosts the backend. Both are run-unique, so
  # concurrent runs never collide on Docker container/node names.
  c1 = var.cluster_name
  c2 = "${var.cluster_name}-peer"
}

# cluster-1 (client/primary). Writes the per-run KUBECONFIG the harness uses.
resource "kind_cluster" "c1" {
  name            = local.c1
  node_image      = var.node_image
  kubeconfig_path = pathexpand(var.kubeconfig_path)
  wait_for_ready  = true
}

# cluster-2 (backend). Writes a SEPARATE kubeconfig so the two resources don't
# clobber the same file during apply; setup.sh merges its context into the per-run
# KUBECONFIG. Both clusters attach to the shared `kind` Docker network by default,
# so their MetalLB-assigned east-west gateway IPs are mutually reachable.
resource "kind_cluster" "c2" {
  name            = local.c2
  node_image      = var.node_image
  kubeconfig_path = pathexpand("${var.kubeconfig_path}-c2")
  wait_for_ready  = true
}

# Outside-the-cluster setup: build the Istio multi-primary federation across both
# clusters and inject the mTLS fault. Runs during `tofu apply`, before the agent.
resource "null_resource" "setup" {
  triggers = {
    c1            = kind_cluster.c1.name
    c2            = kind_cluster.c2.name
    kubeconfig_c2 = pathexpand("${var.kubeconfig_path}-c2")
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = "${path.module}/scripts/setup.sh"
    environment = {
      KUBECONFIG    = pathexpand(var.kubeconfig_path)
      C1            = kind_cluster.c1.name
      C2            = kind_cluster.c2.name
      MANIFESTS_DIR = "${path.module}/manifests"
      ISTIO_VERSION = var.istio_version
    }
  }

  # cluster-2 writes its own kubeconfig file; the kind cluster is destroyed by its
  # resource, but that stray file would linger — remove it on teardown.
  provisioner "local-exec" {
    when       = destroy
    on_failure = continue
    command    = "rm -f '${self.triggers.kubeconfig_c2}'"
  }
}
