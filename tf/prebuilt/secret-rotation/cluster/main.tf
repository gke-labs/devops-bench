terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
  }
}

# 1. GKE Cluster Provisioning
module "gke" {
  source                   = "../../../modules/gke"
  project_id               = var.project_id
  cluster_name             = var.cluster_name
  location                 = var.location
  node_count               = var.node_count
  machine_type             = var.machine_type
  enable_workload_identity = true
  agent_service_account    = "openclaw-vm-sa@${var.project_id}.iam.gserviceaccount.com"
  enable_iap_ssh           = true
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
  account_id   = "sa-${var.namespace}"
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

# 10. Grant permissions to OpenClaw VM Service Account

resource "google_project_iam_member" "openclaw_vm_secret_admin" {
  project = var.project_id
  role    = "roles/secretmanager.admin"
  member  = "serviceAccount:openclaw-vm-sa@${var.project_id}.iam.gserviceaccount.com"
}
