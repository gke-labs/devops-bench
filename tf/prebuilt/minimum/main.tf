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
# for the other tasks on this stack (the repo won't exist).
#
# The repo's region is NOT pinned (the agent picks it, and a multi-region default
# like `us` is common), so deleting at one derived location would miss a repo
# that landed elsewhere. Instead, discover wherever the run-unique repo lives by
# listing the project's repos and delete it at its own location. The name match
# is an exact suffix on the run-unique cluster, so a sibling run's repo is never
# touched.
resource "null_resource" "ar_cleanup" {
  triggers = {
    project = var.project_id
    repo    = "hello-app-${var.cluster_name}"
  }

  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      gcloud artifacts repositories list --project='${self.triggers.project}' \
        --format='value(name)' 2>/dev/null \
      | while IFS= read -r full; do
          case "$full" in
            */repositories/'${self.triggers.repo}')
              loc=$(printf '%s\n' "$full" | sed -E 's#.*/locations/([^/]+)/repositories/.*#\1#')
              gcloud artifacts repositories delete '${self.triggers.repo}' \
                --location="$loc" --project='${self.triggers.project}' \
                --quiet 2>/dev/null || true
              ;;
          esac
        done
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
