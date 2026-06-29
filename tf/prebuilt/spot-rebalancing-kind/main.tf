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
  # Host-side artifact on the shared bastion. setup.sh overwrites it, so a fixed
  # path would let one run clobber a concurrent run's report. cluster_name is
  # run-token-prefixed, making it per-run unique. The task prompt references the
  # same path via the {{CLUSTER_NAME}} placeholder. An explicit override wins.
  report_path = var.report_path != "" ? var.report_path : "~/rightsizing-report-${var.cluster_name}.json"
}

# Multi-node kind cluster: 1 control-plane + 3 workers. setup.sh designates one
# worker as the "on-demand" pool and taints/labels the other two as a reserved
# "spot" pool (control-plane is tainted by kind, so workloads land on workers).
resource "kind_cluster" "default" {
  name            = var.cluster_name
  node_image      = var.node_image
  kubeconfig_path = pathexpand(var.kubeconfig_path)
  wait_for_ready  = true

  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    node {
      role = "control-plane"
    }
    node {
      role = "worker"
    }
    node {
      role = "worker"
    }
    node {
      role = "worker"
    }
  }
}

# Outside-the-cluster setup: label/taint the pools, deploy the fleet, deliver the
# rightsizing report. Runs during `tofu apply`, before the agent starts.
resource "null_resource" "setup" {
  triggers = {
    cluster     = kind_cluster.default.name
    report_path = pathexpand(local.report_path)
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = "${path.module}/scripts/setup.sh"
    environment = {
      KUBECONFIG    = pathexpand(var.kubeconfig_path)
      REPORT_PATH   = pathexpand(local.report_path)
      MANIFESTS_DIR = "${path.module}/manifests"
    }
  }

  # Remove the host-side report on teardown. The kind cluster is destroyed by its
  # own resource; the report lives outside the cluster, so clean it up here so a
  # torn-down run leaves nothing behind on the shared host.
  provisioner "local-exec" {
    when       = destroy
    on_failure = continue
    command    = "rm -f '${self.triggers.report_path}'"
  }
}
