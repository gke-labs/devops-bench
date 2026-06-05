output "cluster_name" {
  value = module.gke.cluster_name
}

output "cluster_location" {
  value = module.gke.cluster_location
}

output "secret_rotation_sa_email" {
  value = google_service_account.secret_rotation_sa.email
}

output "endpoint" {
  value = module.gke.endpoint
}

output "cluster_ca_certificate" {
  value = module.gke.cluster_ca_certificate
}

