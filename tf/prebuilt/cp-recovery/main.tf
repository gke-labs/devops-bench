terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.0.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.15.0"
    }
  }
}

provider "google" {
  project = var.project_id
  zone    = var.location
}

# 1. GKE Cluster & GCP IAM/Secrets provisioning
module "cluster" {
  source       = "./cluster"
  project_id   = var.project_id
  cluster_name = var.cluster_name
  location     = var.location
  node_count   = var.node_count
  machine_type = var.machine_type
  namespace    = var.namespace
}

# 2. Dynamic GKE Credentials Loading
data "google_client_config" "default" {
}

provider "kubernetes" {
  host                   = "https://${module.cluster.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(module.cluster.cluster_ca_certificate)
}

provider "helm" {
  kubernetes {
    host                   = "https://${module.cluster.endpoint}"
    token                  = data.google_client_config.default.access_token
    cluster_ca_certificate = base64decode(module.cluster.cluster_ca_certificate)
  }
}

# 3. Kubernetes resources configuration
module "k8s_config" {
  source                   = "./k8s_config"
  project_id               = var.project_id
  namespace                = var.namespace
  cp_recovery_sa_email     = module.cluster.cp_recovery_sa_email
  etcd_backup_bucket       = module.cluster.etcd_backup_bucket
}

output "cluster_name" {
  value = module.cluster.cluster_name
}

output "cluster_location" {
  value = module.cluster.cluster_location
}
