terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.0.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.15.0"
    }
  }
}

# 1. Helm Release for External Secrets Operator (ESO)
resource "helm_release" "external_secrets" {
  name             = "external-secrets"
  repository       = "https://charts.external-secrets.io"
  chart            = "external-secrets"
  version          = "0.9.11"
  namespace        = "external-secrets"
  create_namespace = true
  # Each run creates a fresh GSA + workload-identity binding; give the ESO
  # install headroom under parallel provisioning.
  timeout = 600

  set {
    name  = "installCRDs"
    value = "true"
  }

  set {
    name  = "serviceAccount.annotations.iam\\.gke\\.io/gcp-service-account"
    value = var.secret_rotation_sa_email
  }
}

# 3. Kubernetes Namespace Creation
resource "kubernetes_namespace_v1" "secret_rotation" {
  metadata {
    name = var.namespace
  }
}

# 4. Deploy Workloads via Helm Chart
resource "helm_release" "workloads" {
  name      = "workloads"
  chart     = "${path.module}/workloads-chart"
  namespace = kubernetes_namespace_v1.secret_rotation.metadata[0].name
  # The app pod blocks until ESO syncs the secret, which blocks on fresh
  # per-run workload-identity propagation. 300s (helm default) is too tight;
  # 900s rides out cold WI bindings. ESO retries every 10s (refreshInterval).
  timeout = 900

  set {
    name  = "projectID"
    value = var.project_id
  }

  set {
    name  = "namespace"
    value = var.namespace
  }

  set {
    name  = "secretName"
    value = var.secret_id
  }

  depends_on = [helm_release.external_secrets]
}
