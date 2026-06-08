variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "cluster_name" {
  description = "The name of the GKE cluster"
  type        = string
}

variable "location" {
  description = "GCP location (region or zone)"
  type        = string
  default     = "us-central1-a"
}

variable "zone" {
  description = "GCP zone for the cluster nodes and Parallelstore instance"
  type        = string
  default     = "us-central1-a"
}

variable "node_count" {
  type    = number
  default = 1
}

variable "machine_type" {
  type    = string
  default = "g2-standard-4"
}
