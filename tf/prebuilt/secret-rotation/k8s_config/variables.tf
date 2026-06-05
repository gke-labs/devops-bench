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

variable "cluster_name" {
  type        = string
  description = "GKE Cluster Name"
}

variable "cluster_location" {
  type        = string
  description = "GKE Cluster Location"
}
