# Copyright 2026 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
  # A kind cluster with no CNI installed never reaches node-Ready on its own;
  # readiness is deferred to null_resource.install_cni's own waits below.
  wait_for_ready = !var.disable_default_cni

  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    networking {
      disable_default_cni = var.disable_default_cni
    }

    node {
      role = "control-plane"
    }

    dynamic "node" {
      for_each = range(max(0, var.node_count - 1))
      content {
        role = "worker"
      }
    }
  }
}

resource "null_resource" "install_cni" {
  count      = var.disable_default_cni ? 1 : 0
  depends_on = [kind_cluster.default]

  triggers = {
    kubeconfig   = pathexpand(var.kubeconfig_path)
    manifest_url = var.cni_manifest_url
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      export KUBECONFIG="${self.triggers.kubeconfig}"
      kubectl apply -f "${self.triggers.manifest_url}"
      kubectl -n kube-system rollout status daemonset/calico-node --timeout='${var.cni_wait_timeout}'
      kubectl wait --for=condition=Ready nodes --all --timeout='${var.cni_wait_timeout}'
    EOT
  }
}

# Duplicates the KinD context to match a GKE-like name pattern.
# This is required for third-party gke-mcp tools to resolve the context when
# running tasks against local KinD clusters, as the MCP client expects the
# context to conform to the "gke_{project}_{location}_{cluster}" format.
resource "null_resource" "duplicate_context" {
  depends_on = [kind_cluster.default]

  triggers = {
    kubeconfig   = pathexpand(var.kubeconfig_path)
    kind_cluster = "kind-${var.cluster_name}"
    kind_user    = "kind-${var.cluster_name}"
    gke_context  = "gke_${var.project_id}_${var.location}_${var.cluster_name}"
  }

  provisioner "local-exec" {
    command = "kubectl --kubeconfig='${self.triggers.kubeconfig}' config set-context '${self.triggers.gke_context}' --cluster='${self.triggers.kind_cluster}' --user='${self.triggers.kind_user}'"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "kubectl --kubeconfig='${self.triggers.kubeconfig}' config delete-context '${self.triggers.gke_context}' || true"
  }
}
