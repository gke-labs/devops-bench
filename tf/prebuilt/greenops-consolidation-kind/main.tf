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
    local = {
      source  = "hashicorp/local"
      version = ">= 2.0.0"
    }
  }
}

provider "kind" {}

locals {
  # Host-side artifact on the shared bastion. cluster_name is run-token-prefixed,
  # making it per-run unique so concurrent runs never collide. The task prompt
  # references the same path via the {{CLUSTER_NAME}} placeholder. An explicit
  # override wins.
  report_path = var.report_path != "" ? var.report_path : "~/carbon-report-${var.cluster_name}.json"
}

# Multi-node kind cluster: 1 control-plane + 4 workers. The workloads run on the
# four workers (control-plane is tainted by kind); the agent consolidates them
# onto fewer workers by cordoning + draining the underutilized ones.
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
    node {
      role = "worker"
    }
  }
}

# Deliver the carbon-aware capacity report declaratively. Managed by TF, so it is
# removed automatically on `tofu destroy` — no teardown shell needed.
resource "local_file" "carbon_report" {
  filename = pathexpand(local.report_path)
  content  = file("${path.module}/manifests/carbon-report.json")
}

# Outside-the-cluster setup: deploy the fleet and wait for it to be Available. The
# kubectl apply isn't expressible as plan-time-safe declarative TF (kind has no
# cluster at plan time), so a thin script remains. Runs during `tofu apply`,
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
      MANIFESTS_DIR = "${path.module}/manifests"
    }
  }
}
