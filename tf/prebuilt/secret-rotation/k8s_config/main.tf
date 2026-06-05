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

# 4. Custom Resource Definitions templates
locals {
  secret_store_yaml = <<-EOT
    apiVersion: external-secrets.io/v1beta1
    kind: ClusterSecretStore
    metadata:
      name: gcp-store
    spec:
      provider:
        gcpsm:
          projectID: "${var.project_id}"
  EOT

  external_secret_yaml = <<-EOT
    apiVersion: external-secrets.io/v1beta1
    kind: ExternalSecret
    metadata:
      name: db-credentials
      namespace: "${var.namespace}"
    spec:
      refreshInterval: 10s
      secretStoreRef:
        kind: ClusterSecretStore
        name: gcp-store
      target:
        name: db-credentials
        creationPolicy: Owner
      data:
        - secretKey: password
          remoteRef:
            key: "db-credentials-${var.namespace}"
            version: "1"
  EOT
}

# 5. Apply CRDs via local-exec to bypass dynamic schema plan connectivity issues
resource "null_resource" "external_secrets_manifests" {
  depends_on = [
    helm_release.external_secrets,
    kubernetes_namespace_v1.secret_rotation
  ]

  triggers = {
    namespace        = var.namespace
    cluster_name     = var.cluster_name
    cluster_location = var.cluster_location
    project_id       = var.project_id
    secret_store_yaml    = local.secret_store_yaml
    external_secret_yaml = local.external_secret_yaml
  }

  provisioner "local-exec" {
    command = <<EOT
      gcloud container clusters get-credentials ${var.cluster_name} --location ${var.cluster_location} --project ${var.project_id}
      rm -rf ~/.kube/cache ~/.kube/http-cache
      sleep 10
      echo '${local.secret_store_yaml}' | kubectl apply -f -
      echo '${local.external_secret_yaml}' | kubectl apply -f -
    EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = <<EOT
      gcloud container clusters get-credentials ${self.triggers.cluster_name} --location ${self.triggers.cluster_location} --project ${self.triggers.project_id}
      echo '${self.triggers.external_secret_yaml}' | kubectl delete -f - --ignore-not-found=true
      echo '${self.triggers.secret_store_yaml}' | kubectl delete -f - --ignore-not-found=true
    EOT
  }
}

# 6. Deploy db-secret-viewer Workload Deployment natively
resource "kubernetes_deployment_v1" "db_secret_viewer" {
  metadata {
    name      = "db-secret-viewer"
    namespace = kubernetes_namespace_v1.secret_rotation.metadata[0].name
    labels = {
      app = "db-secret-viewer"
    }
  }

  spec {
    replicas = 2

    strategy {
      type = "RollingUpdate"
      rolling_update {
        max_surge       = "1"
        max_unavailable = "0"
      }
    }

    selector {
      match_labels = {
        app = "db-secret-viewer"
      }
    }

    template {
      metadata {
        labels = {
          app = "db-secret-viewer"
        }
      }

      spec {
        container {
          name  = "viewer"
          image = "python:3.11-slim"
          command = [
            "python3",
            "-c",
            <<-EOT
            import http.server
            import os
            class Handler(http.server.SimpleHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    try:
                        with open('/etc/db-credentials/password', 'r') as f:
                            val = f.read().strip()
                            self.wfile.write(f"Active Password: {val}\n".encode())
                    except Exception as e:
                        self.wfile.write(f"Error: {str(e)}\n".encode())
            print("Starting server on port 8080...", flush=True)
            http.server.HTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
            EOT
          ]

          port {
            container_port = 8080
          }

          volume_mount {
            name       = "secret-volume"
            mount_path = "/etc/db-credentials"
            read_only  = true
          }

          resources {
            requests = {
              cpu    = "50m"
              memory = "64Mi"
            }
            limits = {
              cpu    = "200m"
              memory = "128Mi"
            }
          }

          readiness_probe {
            http_get {
              path = "/"
              port = 8080
            }
            initial_delay_seconds = 3
            period_seconds        = 5
          }

          liveness_probe {
            http_get {
              path = "/"
              port = 8080
            }
            initial_delay_seconds = 3
            period_seconds        = 10
          }
        }

        volume {
          name = "secret-volume"
          secret {
            secret_name = "db-credentials"
          }
        }
      }
    }
  }

  depends_on = [
    null_resource.external_secrets_manifests
  ]
}

# 7. Deploy db-secret-viewer Workload Service natively
resource "kubernetes_service_v1" "db_secret_viewer" {
  metadata {
    name      = "db-secret-viewer"
    namespace = kubernetes_namespace_v1.secret_rotation.metadata[0].name
  }

  spec {
    selector = {
      app = "db-secret-viewer"
    }

    port {
      port        = 8080
      target_port = 8080
    }
  }
}
