variable "project_id" {
  type = string
}

variable "cluster_name" {
  type = string
}

variable "location" {
  type = string
}

# Passed by the GCP deployer (from NAMESPACE). Unused here but declared to avoid
# an undeclared-variable warning.
variable "namespace" {
  type    = string
  default = "default"
}

variable "start_version" {
  type        = string
  description = "GKE Kubernetes version the cluster starts at (must be within GKE's supported range; the agent upgrades to the next minor)."
  default     = "1.30"
}

variable "repo_path" {
  type        = string
  description = "Local bare git repo the agent clones the manifests from."
  default     = "~/migration-repo.git"
}
