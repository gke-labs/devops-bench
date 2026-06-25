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
  description = "GKE Kubernetes version the cluster starts at (the agent upgrades to the next minor)."
  # NOTE: GKE's supported version range drifts over time, so this default WILL go
  # stale and eventually be rejected ("No valid versions with the prefix ..."). Set
  # it to a currently-supported minor that ALSO has a next minor available; check
  # with: gcloud container get-server-config --zone <zone>
  default = "1.33"
}

variable "repo_path" {
  type        = string
  description = "Local bare git repo the agent clones the manifests from. Empty (default) derives a per-run-unique path from cluster_name so concurrent runs on the shared bastion don't collide (see locals)."
  default     = ""
}
