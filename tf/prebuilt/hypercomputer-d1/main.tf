terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.0.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.0.0"
    }
  }
}

provider "google" {
  project = var.project_id
  zone    = var.location
}

# Per-run random suffix for project-global names (GSA account_id, GCS bucket)
# so concurrent runs of the three wired tasks never collide. The KSA name stays
# the literal hypercomputer-d1-vllm-sa (namespace-scoped; collision-free because
# cluster_name is already run-token-prefixed by the harness, so every run has
# its own cluster and its own copy of the namespace).
resource "random_id" "run" {
  byte_length = 4
}

locals {
  ksa_name        = "hypercomputer-d1-vllm-sa"
  frontend_name   = "hypercomputer-d1-frontend"
  vllm_deployment = "hypercomputer-d1-vllm-server"
  vllm_service    = "hypercomputer-d1-vllm-service"
  vllm_hpa        = "hypercomputer-d1-vllm-hpa"
  bucket_name     = "hypercomputer-d1-models-${var.project_id}-${random_id.run.hex}"
  gsa_account_id  = "hc-d1-vllm-${random_id.run.hex}"

  # Frontend is seeded under two modes; only the USE_GEMINI_API value differs.
  #   - full            : USE_GEMINI_API=false (healthy app, correctly pointed at the local vLLM service)
  #   - broken-frontend : USE_GEMINI_API=true  (the misconfiguration fix-config's agent must repair)
  seed_frontend     = var.seed_mode == "full" || var.seed_mode == "broken-frontend"
  use_gemini_api    = var.seed_mode == "broken-frontend" ? "true" : "false"
  seed_vllm_backend = var.seed_mode == "full"
}

module "cluster" {
  source                   = "../../modules/cluster"
  infra_provider           = "gcp"
  project_id               = var.project_id
  cluster_name             = var.cluster_name
  location                 = var.location
  node_count               = var.node_count
  machine_type             = var.machine_type
  enable_workload_identity = true
}

data "google_client_config" "default" {}

provider "kubernetes" {
  host                   = "https://${module.cluster.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(module.cluster.cluster_ca_certificate)
}

# Shared infra: GCS bucket the vLLM Deployment's gcsfuse volume mounts read-only
# for model weights. We do NOT upload any model files (cost / time): the bucket
# only needs to EXIST so the agent's applied vllm manifest (deploy-config) and
# the seeded vllm pod (get-app-architecture) refer to a real bucket. The vllm
# pod may stay Pending on GPU scheduling — that's fine; the topology is still
# fully inspectable.
resource "google_storage_bucket" "models" {
  name                        = local.bucket_name
  project                     = var.project_id
  location                    = "US"
  force_destroy               = true
  uniform_bucket_level_access = true
}

# Shared infra: GSA bound to the in-cluster KSA via Workload Identity. The KSA
# name is the literal hypercomputer-d1-vllm-sa so it matches the rubric goldens
# and the manifest the agent applies in deploy-config / fix-config.
resource "google_service_account" "vllm_gsa" {
  account_id   = local.gsa_account_id
  display_name = "GSA for hypercomputer-d1 vLLM (Workload Identity -> ${local.ksa_name})"
  project      = var.project_id
}

resource "google_storage_bucket_iam_member" "vllm_gsa_object_viewer" {
  bucket = google_storage_bucket.models.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.vllm_gsa.email}"
}

resource "google_service_account_iam_member" "vllm_workload_identity" {
  service_account_id = google_service_account.vllm_gsa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.namespace}/${local.ksa_name}]"
}

resource "kubernetes_service_account_v1" "vllm" {
  metadata {
    name      = local.ksa_name
    namespace = var.namespace
    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.vllm_gsa.email
    }
  }
}

# ---------------------------------------------------------------------------
# Seeded workloads
# ---------------------------------------------------------------------------
# Frontend Deployment. Seeded under "full" and "broken-frontend"; the only
# difference is the USE_GEMINI_API value. Image / env names / port / KSA all
# match the golden manifest embedded in tasks/gcp/fix-config/task.yaml so the
# topology read back by an agent matches what the task prompt/rubric expect.
resource "kubernetes_deployment_v1" "frontend" {
  count = local.seed_frontend ? 1 : 0

  # Don't block apply on readiness: this is a "resources only" stack (no GPU /
  # no model), so the pod may never become Ready. We only need the Deployment to
  # EXIST for topology inspection / the agent to edit. Without this, apply fails
  # with "Waiting for rollout to finish: 0 replicas Ready".
  wait_for_rollout = false

  metadata {
    name      = local.frontend_name
    namespace = var.namespace
    labels = {
      app = local.frontend_name
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = local.frontend_name
      }
    }

    template {
      metadata {
        labels = {
          app = local.frontend_name
        }
      }

      spec {
        service_account_name            = local.ksa_name
        automount_service_account_token = true

        container {
          name  = "frontend"
          image = "gcr.io/gke-e2e-images/hypercomputer:v1.10"

          env {
            name  = "APP_VERSION"
            value = "v1.10"
          }
          env {
            name  = "VLLM_API_URL"
            value = "http://${local.vllm_service}:8000/v1/chat/completions"
          }
          env {
            name  = "MODEL_NAME"
            value = "google-gemma-3-12b-it"
          }
          env {
            name  = "USE_GEMINI_API"
            value = local.use_gemini_api
          }

          port {
            container_port = 8080
            protocol       = "TCP"
          }
        }
      }
    }
  }

  # fix-config's agent re-applies this Deployment to flip USE_GEMINI_API to
  # "false". Ignore env so a stack re-apply doesn't fight the agent's edit.
  lifecycle {
    ignore_changes = [
      spec[0].template[0].spec[0].container[0].env,
    ]
  }

  depends_on = [kubernetes_service_account_v1.vllm]
}

# vLLM server Deployment (seeded only under "full"). The GPU resource request
# is intentionally OMITTED so the pod can schedule on the standard e2 node pool
# instead of staying permanently Pending — this stack is "resources only" with
# NO GPU node pool and NO model download. The Deployment / Service / HPA shape
# still matches the goldens so the topology is cleanly inspectable for
# get-app-architecture; under real load it would need a GPU pool + populated
# model bucket, which is out of scope for this benchmark.
resource "kubernetes_deployment_v1" "vllm_server" {
  count = local.seed_vllm_backend ? 1 : 0

  # See frontend: no GPU/model in this stack, so the vllm pod stays Pending/not
  # Ready. Don't block apply on rollout — the Deployment/Service/HPA just need to
  # exist so the topology is inspectable.
  wait_for_rollout = false

  metadata {
    name      = local.vllm_deployment
    namespace = var.namespace
    labels = {
      app = local.vllm_deployment
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = local.vllm_deployment
      }
    }

    template {
      metadata {
        labels = {
          app = local.vllm_deployment
        }
        annotations = {
          "gke-gcsfuse/volumes" = "true"
        }
      }

      spec {
        service_account_name             = local.ksa_name
        automount_service_account_token  = true
        share_process_namespace          = false
        termination_grace_period_seconds = 30

        container {
          name    = "vllm"
          image   = "vllm/vllm-openai:latest"
          command = ["/bin/bash", "-c"]
          args = [
            "python3 -m vllm.entrypoints.openai.api_server --model /data/model/google-gemma-3-12b-it --served-model-name google-gemma-3-12b-it --host 0.0.0.0 --port 8000 --trust-remote-code --quantization fp8",
          ]

          port {
            container_port = 8000
            protocol       = "TCP"
          }

          # Generous threshold + delay because the pod will likely never become
          # ready in this NO-GPU stack; readiness shape still matches the golden.
          readiness_probe {
            http_get {
              path   = "/health"
              port   = "8000"
              scheme = "HTTP"
            }
            initial_delay_seconds = 60
            period_seconds        = 10
            timeout_seconds       = 5
            success_threshold     = 1
            failure_threshold     = 30
          }

          volume_mount {
            mount_path        = "/data/model"
            mount_propagation = "None"
            name              = "model-volume"
            read_only         = true
          }
        }

        volume {
          name = "model-volume"
          csi {
            driver    = "gcsfuse.csi.storage.gke.io"
            read_only = false
            volume_attributes = {
              bucketName   = google_storage_bucket.models.name
              mountOptions = "implicit-dirs"
            }
          }
        }
      }
    }
  }

  depends_on = [kubernetes_service_account_v1.vllm]
}

resource "kubernetes_service_v1" "vllm" {
  count = local.seed_vllm_backend ? 1 : 0

  metadata {
    name      = local.vllm_service
    namespace = var.namespace
  }

  spec {
    selector = {
      app = local.vllm_deployment
    }
    type = "ClusterIP"

    port {
      port        = 8000
      target_port = 8000
      protocol    = "TCP"
    }
  }
}

resource "kubernetes_horizontal_pod_autoscaler_v2" "vllm" {
  count = local.seed_vllm_backend ? 1 : 0

  metadata {
    name      = local.vllm_hpa
    namespace = var.namespace
  }

  spec {
    min_replicas = 1
    max_replicas = 10

    scale_target_ref {
      api_version = "apps/v1"
      kind        = "Deployment"
      name        = local.vllm_deployment
    }

    metric {
      type = "Resource"
      resource {
        name = "cpu"
        target {
          type                = "Utilization"
          average_utilization = 60
        }
      }
    }
  }

  depends_on = [kubernetes_deployment_v1.vllm_server]
}
