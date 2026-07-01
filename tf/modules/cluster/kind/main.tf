terraform {
  required_providers {
    kind = {
      source  = "tehcyx/kind"
      version = ">= 0.5.0"
    }
  }
}

resource "kind_cluster" "default" {
  name            = var.cluster_name
  node_image      = var.node_image
  kubeconfig_path = pathexpand(var.kubeconfig_path)
  wait_for_ready  = true
}

resource "null_resource" "rename_context" {
  depends_on = [kind_cluster.default]

  triggers = {
    kubeconfig = var.kubeconfig_path
  }

  provisioner "local-exec" {
    command = "kubectl --kubeconfig=${pathexpand(var.kubeconfig_path)} config rename-context kind-${var.cluster_name} gke_${var.project_id}_${var.location}_${var.cluster_name}"
  }
}
