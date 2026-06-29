terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
    kind = {
      source  = "tehcyx/kind"
      version = ">= 0.5.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0.0"
    }
  }
}

provider "google" {
  project = var.project_id != "" ? var.project_id : null
  region  = var.location != "" && var.location != "local" ? var.location : null
}

provider "kind" {}

# GKE/KinD "production" cluster at the START version. The agent migrates the deprecated
# manifests, validates them, applies them, then performs the upgrade.
module "cluster" {
  source                = "../../modules/cluster"
  cloud_provider        = var.cloud_provider
  project_id            = var.project_id
  cluster_name          = var.cluster_name
  location              = var.location
  node_count            = var.cloud_provider == "gcp" ? 1 : null
  machine_type          = var.cloud_provider == "gcp" ? "e2-standard-4" : null
  kubernetes_version    = var.start_version
  node_image            = var.node_image
  kubeconfig_path       = var.kubeconfig_path
  agent_service_account = var.project_id != "" ? "openclaw-vm-sa@${var.project_id}.iam.gserviceaccount.com" : ""
  enable_iap_ssh        = true
}

# Seed the manifests git repo the agent clones (shared script + manifests — same
# source of truth used by the kind stack).
resource "null_resource" "seed_repo" {
  depends_on = [module.cluster]

  triggers = {
    cluster = module.cluster.cluster_name
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = "${path.module}/scripts/seed-repo.sh"
    environment = {
      REPO_PATH     = pathexpand(var.repo_path)
      MANIFESTS_DIR = "${path.module}/manifests"
    }
  }
}

output "cluster_name" {
  value = module.cluster.cluster_name
}

output "cluster_location" {
  value = module.cluster.location
}
