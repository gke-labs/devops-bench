terraform {
  required_providers {
    kind = {
      source  = "tehcyx/kind"
      version = ">= 0.5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.0.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.15.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0.0"
    }
  }
}

provider "kind" {}

# 1. A real, multi-node kind cluster.
#    Three control-plane nodes give us a real 3-member stacked etcd (Raft quorum,
#    leader election) — the actual control plane we recover, no simulation.
#    One worker hosts the benign workloads (control-plane nodes are tainted).
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
      role = "control-plane"
    }
    node {
      role = "control-plane"
    }
    node {
      role = "worker"
    }
  }
}

# 2. Point the kubernetes/helm providers at the freshly created kind cluster.
provider "kubernetes" {
  host                   = kind_cluster.default.endpoint
  client_certificate     = kind_cluster.default.client_certificate
  client_key             = kind_cluster.default.client_key
  cluster_ca_certificate = kind_cluster.default.cluster_ca_certificate
}

provider "helm" {
  kubernetes {
    host                   = kind_cluster.default.endpoint
    client_certificate     = kind_cluster.default.client_certificate
    client_key             = kind_cluster.default.client_key
    cluster_ca_certificate = kind_cluster.default.cluster_ca_certificate
  }
}

# 3. Benign task resources: desired-state workloads, the GitOps desired state,
#    and the backup volume the verified etcd snapshot is staged into.
resource "helm_release" "workloads" {
  name             = "cp-recovery-workloads"
  chart            = "${path.module}/cp-recovery-chart"
  namespace        = var.namespace
  create_namespace = true

  set {
    name  = "namespace"
    value = var.namespace
  }

  set {
    name  = "clusterName"
    value = var.cluster_name
  }
}

# 4. Fault injection — runs from OUTSIDE the cluster during `tofu apply`
#    (i.e. before the agent ever starts). It takes a verified etcd snapshot,
#    stages it into the backup PVC, then corrupts a single etcd member so the
#    cluster is recoverably degraded (quorum holds, API server stays up).
#    Nothing is left inside the cluster for the agent to read.
resource "null_resource" "inject_fault" {
  depends_on = [helm_release.workloads]

  triggers = {
    cluster   = kind_cluster.default.name
    namespace = var.namespace
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = "${path.module}/scripts/inject-fault.sh"
    environment = {
      CLUSTER_NAME = var.cluster_name
      NAMESPACE    = var.namespace
      KUBECONFIG   = pathexpand(var.kubeconfig_path)
    }
  }
}
