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

# Sweep the Artifact Registry repo the deploy-hello-app agent creates
# (hello-app-<cluster>, project-global and NOT in this stack's tofu state) so it
# doesn't leak across runs — the cluster teardown alone never removes it. No-op
# for the other tasks on this stack (the repo won't exist). Region is derived
# from the zone var (us-central1-a -> us-central1).
resource "null_resource" "ar_cleanup" {
  triggers = {
    project  = var.project_id
    repo     = "hello-app-${var.cluster_name}"
    location = replace(var.location, "/-[a-z]$/", "")
  }

  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      gcloud artifacts repositories delete '${self.triggers.repo}' \
        --location='${self.triggers.location}' --project='${self.triggers.project}' \
        --quiet 2>/dev/null || true
    EOT
  }
}

module "gke" {
  source       = "../../modules/gke"
  project_id   = var.project_id
  cluster_name = var.cluster_name
  location     = var.location
  node_count   = var.node_count
  machine_type = var.machine_type
}


output "cluster_name" {
  value = module.gke.cluster_name
}

output "cluster_location" {
  value = module.gke.cluster_location
}
