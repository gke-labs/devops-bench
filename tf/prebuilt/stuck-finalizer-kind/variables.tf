variable "cluster_name" {
  type        = string
  description = "Name of the kind cluster."
  default     = "devops-bench-kind"
}

variable "location" {
  type        = string
  description = "Always 'local' for kind; kept for deployer compatibility."
  default     = "local"
}

variable "kubeconfig_path" {
  type        = string
  description = "Path kind writes the kubeconfig to (read by the agent)."
  default     = "~/.kube/config"
}

variable "project_id" {
  type        = string
  description = "Matches the KindProvider's local-only default project id, used to build the gke_<project>_<location>_<cluster> context alias the GKE MCP server requires."
  default     = "local-kind"
}

variable "namespace" {
  type        = string
  description = "Namespace whose deletion gets stuck on a custom-resource finalizer."
  default     = "payments-legacy"
}
