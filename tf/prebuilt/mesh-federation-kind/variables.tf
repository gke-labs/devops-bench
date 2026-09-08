variable "cluster_name" {
  type        = string
  description = "Base name for the run. The two kind clusters are '<cluster_name>-a' (client/primary) and '<cluster_name>-b' (backend). The 'cluster_name' output returns the primary so the harness wires KUBECONFIG to it; setup.sh merges the second context in."
  default     = "devops-bench-kind"
}

variable "location" {
  type        = string
  description = "Always 'local' for kind; kept for deployer compatibility."
  default     = "local"
}

variable "kubeconfig_path" {
  type        = string
  description = "Path kind writes the (primary) kubeconfig to; setup.sh merges the second cluster's context into it."
  default     = "~/.kube/config"
}

variable "node_image" {
  type        = string
  description = "Pinned kindest/node image (v1.30.x)."
  default     = "kindest/node:v1.30.0@sha256:047357ac0cfea04663786a612ba1eaba9702bef25227a794b52890dd8bcd692e"
}

variable "istio_version" {
  type        = string
  description = "Pinned Istio version installed on both clusters."
  default     = "1.23.2"
}
