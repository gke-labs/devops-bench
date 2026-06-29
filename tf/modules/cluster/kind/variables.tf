variable "cluster_name" {
  type        = string
  description = "The name of the KinD cluster"
}

variable "kubeconfig_path" {
  type        = string
  description = "Path to write the kubeconfig file"
  default     = "~/.kube/config"
}

variable "node_image" {
  type        = string
  description = "The kind node image to use"
  default     = "kindest/node:v1.29.2"
}
