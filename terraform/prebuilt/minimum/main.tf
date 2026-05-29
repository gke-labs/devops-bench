provider "google" {
  project = var.project_id
  zone    = var.location
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
