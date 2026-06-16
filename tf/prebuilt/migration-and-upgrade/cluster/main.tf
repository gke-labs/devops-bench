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

# Note: the shared GKE module already grants roles/container.admin to
# agent_service_account (openclaw-vm-sa), so the agent can drive the managed
# master + node-pool upgrade — no extra binding needed here.
