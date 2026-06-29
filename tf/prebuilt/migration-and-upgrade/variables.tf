variable "cloud_provider" {
  type        = string
  description = "The target cloud provider (gcp, kind)"
}

variable "project_id" {
  type        = string
  description = "GCP Project ID"
  default     = ""
}

variable "cluster_name" {
  type        = string
  description = "Name of the cluster to provision"
}

variable "location" {
  type        = string
  description = "Region/zone (GCP) or 'local' (KinD)"
}

variable "namespace" {
  type    = string
  default = "default"
}

variable "start_version" {
  type        = string
  description = "GKE Kubernetes version the cluster starts at (the agent upgrades to the next minor)."
  default     = "1.33"
}

variable "node_image" {
  type        = string
  description = "Pinned kindest/node image at the START version the agent upgrades from."
  default     = "kindest/node:v1.30.0@sha256:047357ac0cfea04663786a612ba1eaba9702bef25227a794b52890dd8bcd692e"
}

variable "kubeconfig_path" {
  type        = string
  description = "Path kind writes the kubeconfig to (read by the agent)."
  default     = "~/.kube/config"
}

variable "repo_path" {
  type        = string
  description = "Local bare git repo the agent clones the manifests from. Empty (default) derives a per-run-unique path from cluster_name so concurrent runs on the shared bastion don't collide (see locals)."
  default     = ""
}
