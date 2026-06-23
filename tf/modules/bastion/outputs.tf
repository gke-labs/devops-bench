output "sa_email" {
  description = "Email of the service account the bastion runs as."
  value       = google_service_account.bastion.email
}

output "name" {
  description = "Name of the bastion VM."
  value       = google_compute_instance.bastion.name
}

output "zone" {
  description = "Zone of the bastion VM."
  value       = google_compute_instance.bastion.zone
}

output "iap_ssh_command" {
  description = "Command to SSH into the bastion over IAP."
  value       = "gcloud compute ssh ${google_compute_instance.bastion.name} --zone ${google_compute_instance.bastion.zone} --project ${var.project_id} --tunnel-through-iap"
}
