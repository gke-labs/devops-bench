output "cluster_name" {
  value = module.cluster.cluster_name
}

output "cluster_location" {
  value = module.cluster.location
}

output "secret_rotation_sa_email" {
  value = google_service_account.secret_rotation_sa.email
}

output "secret_id" {
  description = "The (run-suffixed) Secret Manager secret id the ExternalSecret must reference."
  value       = google_secret_manager_secret.db_credentials.secret_id
}

output "cache_secret_id" {
  description = "Decoy: uncompromised sibling secret, must be left untouched."
  value       = google_secret_manager_secret.cache_credentials.secret_id
}

output "webhook_secret_id" {
  description = "Decoy: uncompromised sibling secret, must be left untouched."
  value       = google_secret_manager_secret.webhook_signing_key.secret_id
}

output "endpoint" {
  value = module.cluster.endpoint
}

output "cluster_ca_certificate" {
  value = module.cluster.cluster_ca_certificate
}

