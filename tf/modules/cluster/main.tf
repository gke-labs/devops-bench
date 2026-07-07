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
  }
}

module "gke" {
  source                   = "./gke"
  count                    = var.infra_provider == "gcp" ? 1 : 0
  project_id               = var.project_id
  location                 = var.location != "" ? var.location : "us-central1-a"
  cluster_name             = var.cluster_name
  node_count               = var.node_count
  machine_type             = var.machine_type != "" ? var.machine_type : "e2-standard-2"
  kubernetes_version       = var.kubernetes_version
  enable_workload_identity = var.enable_workload_identity
  agent_service_account    = var.agent_service_account
  enable_iap_ssh           = var.enable_iap_ssh
  gpu_type                 = var.gpu_type
  gpu_count                = var.gpu_count
}

module "kind" {
  source          = "./kind"
  count           = var.infra_provider == "kind" ? 1 : 0
  cluster_name    = var.cluster_name
  kubeconfig_path = var.kubeconfig_path
  node_image      = var.node_image
  project_id      = var.project_id
  location        = var.location != "" ? var.location : "local"
}

