terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
  }
}

module "gke" {
  source       = "../../../modules/gke"
  project_id   = var.project_id
  cluster_name = var.cluster_name
  location     = var.location
  node_count   = var.node_count
  machine_type = var.machine_type
  agent_service_account = "openclaw-vm-sa@${var.project_id}.iam.gserviceaccount.com"
  enable_iap_ssh        = true
}

resource "google_storage_bucket" "etcd_backup" {
  name                        = "cpr-${var.project_id}-${var.namespace}"
  location                    = "US"
  force_destroy               = true
  project                     = var.project_id
  uniform_bucket_level_access = true
}

locals {
  gke_node_sa_email = "gke-nodes-${trim(substr(var.cluster_name, 0, 15), "-")}@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_service_account" "cp_recovery_sa" {
  account_id   = "cp-recovery-sa"
  display_name = "GSA for GKE Control Plane Recovery access"
  project      = var.project_id
}

resource "google_storage_bucket_iam_member" "gsa_bucket_access" {
  bucket = google_storage_bucket.etcd_backup.name
  role   = "roles/storage.admin"
  member = "serviceAccount:${google_service_account.cp_recovery_sa.email}"
}

resource "google_storage_bucket_iam_member" "openclaw_vm_bucket_access" {
  bucket = google_storage_bucket.etcd_backup.name
  role   = "roles/storage.admin"
  member = "serviceAccount:openclaw-vm-sa@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_storage_bucket_iam_member" "gke_nodes_bucket_access" {
  bucket = google_storage_bucket.etcd_backup.name
  role   = "roles/storage.admin"
  member = "serviceAccount:${local.gke_node_sa_email}"
}

resource "google_service_account_iam_member" "setup_workload_identity" {
  service_account_id = google_service_account.cp_recovery_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.namespace}/cp-recovery-setup-sa]"
}


