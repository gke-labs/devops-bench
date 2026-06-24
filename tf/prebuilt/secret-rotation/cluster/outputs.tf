output "cluster_name" {
  value = module.gke.cluster_name
}

output "cluster_location" {
  value = module.gke.cluster_location
}

output "secret_rotation_sa_email" {
  value = google_service_account.secret_rotation_sa.email
}

output "secret_id" {
  description = "The (run-suffixed) Secret Manager secret id the ExternalSecret must reference."
  value       = google_secret_manager_secret.db_credentials.secret_id
}

output "endpoint" {
  value = module.gke.endpoint
}

output "cluster_ca_certificate" {
  value = module.gke.cluster_ca_certificate
}

