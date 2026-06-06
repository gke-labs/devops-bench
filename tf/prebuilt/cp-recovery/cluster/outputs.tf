output "cluster_name" {
  value = module.gke.cluster_name
}

output "cluster_location" {
  value = module.gke.cluster_location
}

output "endpoint" {
  value = module.gke.endpoint
}

output "cluster_ca_certificate" {
  value = module.gke.cluster_ca_certificate
}

output "cp_recovery_sa_email" {
  value = google_service_account.cp_recovery_sa.email
}

output "etcd_backup_bucket" {
  value = google_storage_bucket.etcd_backup.name
}
