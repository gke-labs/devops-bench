output "cluster_name" {
  value       = var.infra_provider == "gcp" ? try(module.gke[0].cluster_name, "") : try(module.kind[0].cluster_name, "")
  description = "The finalized name of the created cluster"
}

output "location" {
  value       = var.infra_provider == "gcp" ? try(module.gke[0].cluster_location, "") : try(module.kind[0].cluster_location, "")
  description = "The region/zone or 'local'"
}

output "endpoint" {
  value       = var.infra_provider == "gcp" ? try(module.gke[0].endpoint, "") : try(module.kind[0].endpoint, "")
  description = "Cluster control plane endpoint"
}

output "cluster_ca_certificate" {
  value       = var.infra_provider == "gcp" ? try(module.gke[0].cluster_ca_certificate, "") : try(module.kind[0].cluster_ca_certificate, "")
  description = "Cluster CA certificate"
}

output "client_certificate" {
  value       = var.infra_provider == "kind" ? try(module.kind[0].client_certificate, "") : ""
  description = "Client certificate for KinD"
}

output "client_key" {
  value       = var.infra_provider == "kind" ? try(module.kind[0].client_key, "") : ""
  description = "Client key for KinD"
}

output "kubeconfig_path" {
  value       = var.infra_provider == "kind" ? try(module.kind[0].kubeconfig_path, "") : ""
  description = "Local path to the kubeconfig file"
}

