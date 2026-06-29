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

variable "node_image" {
  type        = string
  description = "Pinned kindest/node image (v1.30.x)."
  default     = "kindest/node:v1.30.0@sha256:047357ac0cfea04663786a612ba1eaba9702bef25227a794b52890dd8bcd692e"
}

variable "report_path" {
  type        = string
  description = "Local file the rightsizing (VPA) report is delivered to (read by the agent). Empty (default) derives a per-run-unique path from cluster_name so concurrent runs don't clobber each other's report (see locals)."
  default     = ""
}
