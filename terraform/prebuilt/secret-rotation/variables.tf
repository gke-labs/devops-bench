variable "project_id" {
  type        = string
  description = "GCP Project ID"
}

variable "cluster_name" {
  type        = string
  description = "GKE Cluster Name"
}

variable "location" {
  type        = string
  description = "GCP location/zone where GKE cluster is provisioned"
  default     = "us-central1-a"
}

variable "node_count" {
  type        = number
  description = "Number of GKE nodes"
  default     = 3
}

variable "machine_type" {
  type        = string
  description = "Machine type for GKE nodes"
  default     = "e2-standard-2"
}

variable "namespace" {
  type        = string
  description = "Kubernetes Namespace to deploy secret rotation test app"
  default     = "secret-rotation"
}
