variable "cluster_name" {
  type        = string
  description = "Name of the kind cluster (also used as the docker container name prefix)."
  default     = "devops-bench-kind"
}

variable "namespace" {
  type        = string
  description = "Namespace the task workloads are provisioned into."
  default     = "cp-recovery"
}

variable "location" {
  type        = string
  description = "Cluster location. Always 'local' for kind; kept for deployer compatibility."
  default     = "local"
}

variable "kubeconfig_path" {
  type        = string
  description = "Path kind writes the kubeconfig to (read by the agent + provisioners)."
  default     = "~/.kube/config"
}

variable "node_image" {
  type        = string
  description = "Pinned kindest/node image (v1.30.x for ValidatingAdmissionPolicy + stable etcd layout)."
  default     = "kindest/node:v1.30.0@sha256:047357ac0cfea04663786a612ba1eaba9702bef25227a794b52890dd8bcd692e"
}
