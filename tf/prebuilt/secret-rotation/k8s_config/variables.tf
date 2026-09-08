variable "project_id" {
  type        = string
  description = "GCP Project ID"
}

variable "namespace" {
  type        = string
  description = "Kubernetes Namespace"
}

variable "secret_rotation_sa_email" {
  type        = string
  description = "GCP IAM Service Account Email for Workload Identity annotation"
}

variable "secret_id" {
  type        = string
  description = "Run-suffixed Secret Manager secret id the ExternalSecret references."
}

variable "cache_secret_id" {
  type        = string
  description = "Decoy: uncompromised sibling secret id, must be left untouched."
}

variable "webhook_secret_id" {
  type        = string
  description = "Decoy: uncompromised sibling secret id, must be left untouched."
}

