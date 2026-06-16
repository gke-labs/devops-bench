terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
  }
}

module "gke" {
  source                = "../../../modules/gke"
  project_id            = var.project_id
  cluster_name          = var.cluster_name
  location              = var.location
  node_count            = 1
  machine_type          = "e2-standard-4"
  kubernetes_version    = var.kubernetes_version
  agent_service_account = "openclaw-vm-sa@${var.project_id}.iam.gserviceaccount.com"
  enable_iap_ssh        = true
}

# The agent (running as the openclaw VM SA) needs to drive the managed master +
# node-pool version upgrade, so grant it container admin on this project.
resource "google_project_iam_member" "openclaw_vm_container_admin" {
  project = var.project_id
  role    = "roles/container.admin"
  member  = "serviceAccount:openclaw-vm-sa@${var.project_id}.iam.gserviceaccount.com"
}
