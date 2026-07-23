output "cluster_name" {
  value = module.cluster.cluster_name
}

output "cluster_location" {
  value = module.cluster.location
}

output "models_bucket" {
  value       = google_storage_bucket.models.name
  description = "GCS bucket the vLLM Deployment's gcsfuse volume references for model weights."
}

output "vllm_gsa_email" {
  value       = google_service_account.vllm_gsa.email
  description = "GSA bound to KSA hypercomputer-d1-vllm-sa via Workload Identity."
}
