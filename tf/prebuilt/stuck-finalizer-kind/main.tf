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

# Single-node kind cluster. The /dev/kmsg mount is a no-op on a normal host
# (which already has a real /dev/kmsg) but is required when Docker runs inside
# a nested LXD/container sandbox that has no kernel message device of its own -
# kubelet fails to start with "open /dev/kmsg: no such file or directory"
# without it.
resource "kind_cluster" "default" {
  name            = var.cluster_name
  kubeconfig_path = pathexpand(var.kubeconfig_path)
  wait_for_ready  = true

  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    node {
      role = "control-plane"
      extra_mounts {
        host_path      = "/dev/kmsg"
        container_path = "/dev/kmsg"
      }
    }
  }
}

# Outside-the-cluster setup: creates the CRD + namespace + stuck custom
# resource fixture, and seeds the gke_<project>_<location>_<cluster>
# kubeconfig context the GKE MCP server's k8s tools require (they always
# resolve that literal context name, never the cluster's "real" kind context).
resource "null_resource" "setup" {
  triggers = {
    cluster = kind_cluster.default.name
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = "${path.module}/scripts/setup.sh"
    environment = {
      KUBECONFIG   = pathexpand(var.kubeconfig_path)
      CLUSTER_NAME = var.cluster_name
      PROJECT_ID   = var.project_id
      LOCATION     = var.location
      NAMESPACE    = var.namespace
      MANIFEST_DIR = "${path.module}/manifests"
    }
  }
}
