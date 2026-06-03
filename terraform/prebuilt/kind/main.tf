terraform {
  required_providers {
    kind = {
      source  = "tehcyx/kind"
      version = ">= 0.5.0"
    }
  }
}

provider "kind" {}

resource "kind_cluster" "default" {
  name            = var.cluster_name
  wait_for_ready  = true
  kubeconfig_path = pathexpand(var.kubeconfig_path)
}

output "cluster_name" {
  value = kind_cluster.default.name
}

output "cluster_location" {
  value = "local"
}
