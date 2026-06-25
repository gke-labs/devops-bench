variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "location" {
  description = "The GCP zone or region"
  type        = string
  default     = "us-central1-a"
}

variable "cluster_name" {
  description = "The name of the GKE cluster"
  type        = string
}

variable "node_count" {
  description = "Number of nodes in the standard pool"
  type        = number
  default     = 3
}

variable "machine_type" {
  description = "Machine type for the nodes"
  type        = string
  default     = "e2-standard-2"
}

variable "enable_workload_identity" {
  description = "Enable GKE Workload Identity"
  type        = bool
  default     = false
}

variable "kubernetes_version" {
  description = "The Kubernetes version for the GKE cluster"
  type        = string
  default     = null
}

variable "agent_service_account" {
  description = "The service account email of the agent"
  type        = string
  default     = ""
}

variable "enable_iap_ssh" {
  description = "Enable IAP SSH firewall rule for the cluster"
  type        = bool
  default     = false
}
