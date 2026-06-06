terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
  }
}

provider "google" {
  project = var.project_id
  zone    = var.location
}

# 1. GKE Cluster provisioning
module "cluster" {
  source       = "./cluster"
  project_id   = var.project_id
  cluster_name = var.cluster_name
  location     = var.location
}

# 2. Cloud Source Repository with Manifests
module "csr" {
  source     = "./csr"
  project_id = var.project_id
  namespace  = var.namespace
  depends_on = [module.cluster]
}

output "cluster_name" {
  value = module.cluster.cluster_name
}

output "cluster_location" {
  value = module.cluster.cluster_location
}
