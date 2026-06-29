output "cluster_name" {
  value       = var.cloud_provider == "gcp" ? try(module.gke[0].cluster_name, "") : try(module.kind[0].cluster_name, "")
  description = "The finalized name of the created cluster"
}

output "location" {
  value       = var.cloud_provider == "gcp" ? try(module.gke[0].cluster_location, "") : try(module.kind[0].cluster_location, "")
  description = "The region/zone or 'local'"
}

output "endpoint" {
  value       = var.cloud_provider == "gcp" ? try(module.gke[0].endpoint, "") : "127.0.0.1"
  description = "Cluster control plane endpoint"
}

output "cluster_ca_certificate" {
  value       = var.cloud_provider == "gcp" ? try(module.gke[0].cluster_ca_certificate, "") : ""
  description = "Cluster CA certificate"
}

output "kubeconfig_path" {
  value       = var.cloud_provider == "kind" ? try(module.kind[0].kubeconfig_path, "") : ""
  description = "Local path to the kubeconfig file"
}
