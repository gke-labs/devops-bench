terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
  }
}

module "gke" {
  source             = "../../../modules/gke"
  project_id         = var.project_id
  cluster_name       = var.cluster_name
  location           = var.location
  node_count         = 1
  machine_type       = "e2-standard-4"
  kubernetes_version    = "1.33" # This will pick the default 1.33.x version
  agent_service_account = "openclaw-vm-sa@${var.project_id}.iam.gserviceaccount.com"
  enable_iap_ssh        = true
}

resource "google_project_iam_member" "openclaw_vm_source_admin" {
  project = var.project_id
  role    = "roles/source.admin"
  member  = "serviceAccount:openclaw-vm-sa@${var.project_id}.iam.gserviceaccount.com"
}
