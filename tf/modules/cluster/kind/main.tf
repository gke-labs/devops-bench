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

resource "null_resource" "duplicate_context" {
  depends_on = [kind_cluster.default]

  triggers = {
    kubeconfig   = pathexpand(var.kubeconfig_path)
    kind_cluster = "kind-${var.cluster_name}"
    kind_user    = "kind-${var.cluster_name}"
    gke_context  = "gke_${var.project_id}_${var.location}_${var.cluster_name}"
  }

  provisioner "local-exec" {
    command = "kubectl --kubeconfig=${self.triggers.kubeconfig} config set-context ${self.triggers.gke_context} --cluster=${self.triggers.kind_cluster} --user=${self.triggers.kind_user}"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "kubectl --kubeconfig=${self.triggers.kubeconfig} config delete-context ${self.triggers.gke_context} || true"
  }
}
