variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "cluster_name" {
  description = "The name of the GKE cluster (run-token-prefixed under parallel runs)"
  type        = string
}

variable "location" {
  description = "GCP zone or region for the cluster"
  type        = string
  default     = "us-central1-a"
}

variable "node_count" {
  type    = number
  default = 3
}

variable "machine_type" {
  type    = string
  default = "e2-standard-2"
}

variable "namespace" {
  description = "Namespace the target workload is deployed into. Must match the harness {{NAMESPACE}} placeholder. 'default' always exists; any other value must be pre-created."
  type        = string
  default     = "default"
}

variable "target_deployment_name" {
  description = "Name of the pre-seeded Deployment + Service the agent must optimize. Must match the harness {{TARGET_DEPLOYMENT_NAME}} placeholder."
  type        = string
  default     = "scale-target"
}
