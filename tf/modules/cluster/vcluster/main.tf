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
  required_version = ">= 1.5.0"
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.25"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0"
    }
  }
}


resource "kubernetes_namespace" "vcluster" {
  metadata {
    name = var.namespace
    labels = {
      app                       = "vcluster"
      "devops-bench/run-scoped" = "true"
    }
  }
}

resource "kubernetes_service" "vcluster_exposure" {
  metadata {
    name      = var.cluster_name
    namespace = kubernetes_namespace.vcluster.metadata[0].name
  }

  spec {
    type = var.service_type
    selector = {
      app     = "vcluster"
      release = var.cluster_name
    }
    port {
      port        = 443
      target_port = 8443
      protocol    = "TCP"
      node_port   = var.node_port
    }
  }

  lifecycle {
    ignore_changes = [spec[0].port[0].node_port]
  }
}

resource "kubernetes_resource_quota" "vcluster_quota" {
  metadata {
    name      = "vcluster-quota"
    namespace = kubernetes_namespace.vcluster.metadata[0].name
  }

  spec {
    hard = {
      "limits.cpu"             = var.quota_cpu
      "limits.memory"          = var.quota_memory
      "requests.cpu"           = var.quota_cpu
      "requests.memory"        = var.quota_memory
      "requests.storage"       = var.quota_storage
      "persistentvolumeclaims" = var.quota_pvc
    }
  }
}

resource "kubernetes_limit_range" "vcluster_limits" {
  metadata {
    name      = "vcluster-limits"
    namespace = kubernetes_namespace.vcluster.metadata[0].name
  }

  spec {
    limit {
      type = "Container"
      # Defaults sized so a full task seed fits the namespace quota above.
      # With the virtual cluster's own quota disabled (see values.yaml.tftpl),
      # every limit-less container synced from the vcluster gets these — at
      # 1 CPU each, Kyverno's four controllers plus the vcluster control
      # plane, CoreDNS, and a task's limit-less workloads brush the 7-CPU
      # quota ceiling; 500m keeps the same seed at roughly half of it.
      default = {
        cpu    = var.limit_default_cpu
        memory = var.limit_default_memory
      }
      default_request = {
        cpu    = var.limit_request_cpu
        memory = var.limit_request_memory
      }
      max = {
        cpu    = var.limit_max_cpu
        memory = var.limit_max_memory
      }
    }
  }
}

data "kubernetes_nodes" "host_nodes" {}

locals {
  host_node_ip = try(
    coalesce(
      try([for a in data.kubernetes_nodes.host_nodes.nodes[0].status[0].addresses : a.address if a.type == "ExternalIP"][0], null),
      try([for a in data.kubernetes_nodes.host_nodes.nodes[0].status[0].addresses : a.address if a.type == "InternalIP"][0], null),
      "127.0.0.1"
    ),
    "127.0.0.1"
  )
  external_endpoint = var.service_type == "NodePort" ? "${local.host_node_ip}:${kubernetes_service.vcluster_exposure.spec[0].port[0].node_port}" : try(coalesce(kubernetes_service.vcluster_exposure.status[0].load_balancer[0].ingress[0].ip, kubernetes_service.vcluster_exposure.status[0].load_balancer[0].ingress[0].hostname), "")
}

resource "helm_release" "vcluster" {
  name          = var.cluster_name
  namespace     = kubernetes_namespace.vcluster.metadata[0].name
  repository    = endswith(var.chart_name_or_path, ".tgz") ? null : var.chart_repository
  chart         = var.chart_name_or_path
  version       = endswith(var.chart_name_or_path, ".tgz") ? null : var.chart_version
  wait          = true
  wait_for_jobs = true

  values = [
    templatefile("${path.module}/values.yaml.tftpl", {
      endpoint     = local.external_endpoint
      cluster_name = var.cluster_name != null && var.cluster_name != "" ? var.cluster_name : "devops-bench-vcluster"
      service_cidr = var.service_cidr != null ? var.service_cidr : ""
    })
  ]

  lifecycle {
    precondition {
      condition     = local.external_endpoint != "" && !endswith(local.external_endpoint, ":")
      error_message = "The external endpoint is not yet assigned. For service_type = LoadBalancer, ensure the cloud provider has assigned an ingress IP or hostname. For NodePort, ensure a node port is assigned."
    }
  }

  depends_on = [
    kubernetes_service.vcluster_exposure,
    kubernetes_resource_quota.vcluster_quota,
    kubernetes_limit_range.vcluster_limits
  ]
}

resource "null_resource" "wait_for_vcluster_secret" {
  depends_on = [helm_release.vcluster]

  triggers = {
    release = helm_release.vcluster.id
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOT
      ctx_flag=""
      if [ -n "${var.host_kubecontext}" ]; then
        ctx_flag="--context=${var.host_kubecontext}"
      fi
      for i in $(seq 1 30); do
        secret_json=$(kubectl --kubeconfig="${pathexpand(var.host_kubeconfig_path)}" $ctx_flag get secret "vc-${var.cluster_name}" -n "${kubernetes_namespace.vcluster.metadata[0].name}" -o json 2>/dev/null || true)
        if echo "$secret_json" | grep -q '"config"'; then
          exit 0
        fi
        sleep 2
      done
      echo "Timed out waiting for vcluster secret vc-${var.cluster_name} to be populated" >&2
      exit 1
    EOT
  }
}

data "kubernetes_secret" "vcluster_kubeconfig" {
  metadata {
    name      = "vc-${var.cluster_name}"
    namespace = kubernetes_namespace.vcluster.metadata[0].name
  }

  depends_on = [null_resource.wait_for_vcluster_secret]
}
