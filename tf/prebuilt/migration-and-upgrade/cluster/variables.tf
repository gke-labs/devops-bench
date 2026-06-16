variable "project_id" {
  type = string
}

variable "cluster_name" {
  type = string
}

variable "location" {
  type = string
}

variable "kubernetes_version" {
  type        = string
  description = "Kubernetes version the cluster is created at (the START version for the upgrade). Overridden by the root start_version; keep in sync. Must be a currently-supported GKE minor (the range drifts over time)."
  default     = "1.33"
}
