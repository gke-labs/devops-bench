variable "cluster_name" {
  type    = string
  default = "devops-bench-kind"
}

variable "location" {
  type    = string
  default = "local"
}

variable "kubeconfig_path" {
  type        = string
  description = "Path to write the kubeconfig file"
  default     = "~/.kube/config"
}

