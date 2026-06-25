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

