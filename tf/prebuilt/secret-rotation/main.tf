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
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.15.0"
    }
  }
}

provider "google" {
  project = var.project_id
  zone    = var.location
}

# 1. GKE Cluster Provisioning
module "gke" {
  source       = "../../modules/gke"
  project_id   = var.project_id
  cluster_name = var.cluster_name
  location     = var.location
  node_count   = var.node_count
  machine_type = var.machine_type
}

# 2. Dynamic GKE Credentials Loading
data "google_client_config" "default" {}

data "google_container_cluster" "primary" {
  name     = module.gke.cluster_name
  location = module.gke.cluster_location
  project  = var.project_id

  depends_on = [module.gke]
}

provider "kubernetes" {
  host                   = "https://${data.google_container_cluster.primary.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(data.google_container_cluster.primary.master_auth[0].cluster_ca_certificate)
}

provider "helm" {
  kubernetes {
    host                   = "https://${data.google_container_cluster.primary.endpoint}"
    token                  = data.google_client_config.default.access_token
    cluster_ca_certificate = base64decode(data.google_container_cluster.primary.master_auth[0].cluster_ca_certificate)
  }
}

# 3. GCP Secret Manager Setup
resource "google_secret_manager_secret" "db_credentials" {
  secret_id = "db-credentials-${var.namespace}"
  project   = var.project_id
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_credentials_v1" {
  secret      = google_secret_manager_secret.db_credentials.id
  secret_data = "compromised-password-v1"
}

# 4. GCP IAM & GSA Configuration
resource "google_service_account" "secret_rotation_sa" {
  account_id   = "secret-rotation-sa"
  display_name = "GSA for GKE ExternalSecrets Secret Manager access"
  project      = var.project_id
}

resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.secret_rotation_sa.email}"
}

resource "google_service_account_iam_member" "workload_identity" {
  service_account_id = google_service_account.secret_rotation_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[external-secrets/external-secrets]"
}

# 5. Helm Release for External Secrets Operator (ESO)
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
}

# 6. Kubernetes SA Annotation for Workload Identity
resource "kubernetes_annotations" "external_secrets_sa" {
  api_version = "v1"
  kind        = "ServiceAccount"
  metadata {
    name      = "external-secrets"
    namespace = "external-secrets"
  }
  annotations = {
    "iam.gke.io/gcp-service-account" = google_service_account.secret_rotation_sa.email
  }

  depends_on = [helm_release.external_secrets]
}

# 7. Kubernetes Namespace Creation
resource "kubernetes_namespace" "secret_rotation" {
  metadata {
    name = var.namespace
  }
}

# 8. Rendered manifests
resource "local_file" "secret_store_yaml" {
  content  = replace(file("${path.module}/secret-store.yaml"), "{{GCP_PROJECT_ID}}", var.project_id)
  filename = "${path.module}/secret-store-rendered.yaml"
}

resource "local_file" "external_secret_yaml" {
  content  = replace(
    replace(file("${path.module}/external-secret.yaml"), "{{NAMESPACE}}", var.namespace),
    "{{SECRET_ID}}",
    "db-credentials-${var.namespace}"
  )
  filename = "${path.module}/external-secret-rendered.yaml"
}

resource "local_file" "deployment_yaml" {
  content  = replace(file("${path.module}/deployment.yaml"), "{{NAMESPACE}}", var.namespace)
  filename = "${path.module}/deployment-rendered.yaml"
}

# 9. Apply manifests inside GKE cluster using local-exec provisioner
resource "null_resource" "kubernetes_manifests" {
  depends_on = [
    module.gke,
    helm_release.external_secrets,
    kubernetes_namespace.secret_rotation,
    local_file.secret_store_yaml,
    local_file.external_secret_yaml,
    local_file.deployment_yaml
  ]

  triggers = {
    cluster_name         = module.gke.cluster_name
    cluster_location     = module.gke.cluster_location
    project_id           = var.project_id
    secret_store_path    = local_file.secret_store_yaml.filename
    external_secret_path = local_file.external_secret_yaml.filename
    deployment_path      = local_file.deployment_yaml.filename
  }

  provisioner "local-exec" {
    command = <<EOT
      gcloud container clusters get-credentials ${module.gke.cluster_name} --location ${module.gke.cluster_location} --project ${var.project_id}
      kubectl apply -f ${local_file.secret_store_yaml.filename}
      kubectl apply -f ${local_file.external_secret_yaml.filename}
      kubectl apply -f ${local_file.deployment_yaml.filename}
    EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = <<EOT
      gcloud container clusters get-credentials ${self.triggers.cluster_name} --location ${self.triggers.cluster_location} --project ${self.triggers.project_id}
      kubectl delete -f ${self.triggers.secret_store_path} --ignore-not-found=true
      kubectl delete -f ${self.triggers.external_secret_path} --ignore-not-found=true
      kubectl delete -f ${self.triggers.deployment_path} --ignore-not-found=true
    EOT
  }
}

resource "google_compute_firewall" "allow_iap_ssh" {
  name    = "allow-iap-ssh-default"
  network = "default"
  project = var.project_id

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"]
}

# 11. Grant permissions to OpenClaw VM Service Account
resource "google_project_iam_member" "openclaw_vm_container_admin" {
  project = var.project_id
  role    = "roles/container.admin"
  member  = "serviceAccount:openclaw-vm-sa@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "openclaw_vm_secret_admin" {
  project = var.project_id
  role    = "roles/secretmanager.admin"
  member  = "serviceAccount:openclaw-vm-sa@${var.project_id}.iam.gserviceaccount.com"
}


output "cluster_name" {
  value = module.gke.cluster_name
}

output "cluster_location" {
  value = module.gke.cluster_location
}
