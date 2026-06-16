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
  description = "Kubernetes version the cluster is created at (the START version for the upgrade)."
  default     = "1.30"
}
