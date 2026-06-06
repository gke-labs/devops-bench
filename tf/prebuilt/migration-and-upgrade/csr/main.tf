terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
  }
}

resource "google_project_service" "sourcerepo" {
  project            = var.project_id
  service            = "sourcerepo.googleapis.com"
  disable_on_destroy = false
}

resource "google_sourcerepo_repository" "repo" {
  name       = "${var.namespace}-repo"
  project    = var.project_id
  depends_on = [google_project_service.sourcerepo]
}

resource "null_resource" "push_manifests" {
  depends_on = [google_sourcerepo_repository.repo]

  provisioner "local-exec" {
    command = <<EOT
      set -e
      REPO_DIR=$(mktemp -d)
      gcloud source repos clone ${google_sourcerepo_repository.repo.name} $REPO_DIR --project=${var.project_id}
      
      cp ${path.module}/manifests/* $REPO_DIR/
      cd $REPO_DIR
      
      git config user.email "terraform@example.com"
      git config user.name "Terraform"
      
      git add .
      git commit -m "Initial commit with deprecated manifests"
      git push origin HEAD:master
      
      rm -rf $REPO_DIR
    EOT
  }
}
