variable "cluster_name" {
  type        = string
  description = "Name of the kind cluster (run-token-prefixed by the harness)."
  default     = "devops-bench-kind"
}

variable "location" {
  type        = string
  description = "Always 'local' for kind; kept for deployer compatibility."
  default     = "local"
}

variable "kubeconfig_path" {
  type        = string
  description = "Path kind writes the kubeconfig to (read by the agent). The harness injects the per-run KUBECONFIG."
  default     = "~/.kube/config"
}

variable "node_image" {
  type        = string
  description = "Pinned kindest/node image."
  default     = "kindest/node:v1.30.0@sha256:047357ac0cfea04663786a612ba1eaba9702bef25227a794b52890dd8bcd692e"
}

variable "namespace" {
  type        = string
  description = "Namespace the broken 'frontend' fixture is applied to. Must match the prompt's {{NAMESPACE}}."
  default     = "default"
}
