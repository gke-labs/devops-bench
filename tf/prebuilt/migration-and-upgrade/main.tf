terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0.0"
    }
  }
}

provider "google" {
  project = var.project_id
  zone    = var.location
}

# GKE "production" cluster at the START version. The agent migrates the deprecated
# manifests, validates them, applies them, then performs the managed master +
# node-pool upgrade to the target version.
module "cluster" {
  source             = "./cluster"
  project_id         = var.project_id
  cluster_name       = var.cluster_name
  location           = var.location
  kubernetes_version = var.start_version
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
  value = module.cluster.cluster_location
}
