variable "infra_provider" {
  type        = string
  description = "The target cloud provider (gcp, kind)"
}

variable "cluster_name" {
  type        = string
  description = "Name of the cluster to provision"
}

variable "location" {
  type        = string
  description = "Region/zone (GCP) or 'local' (KinD)"
  default     = ""
}

variable "node_count" {
  type        = number
  description = "Number of worker nodes"
  default     = 3
}

variable "machine_type" {
  type        = string
  description = "VM instance type"
  default     = ""
}

# Provider-specific optional variables
variable "project_id" {
  type        = string
  description = "GCP Project ID"
  default     = ""
}

variable "kubeconfig_path" {
  type        = string
  description = "Target path to write kubeconfig (KinD-only)"
  default     = "~/.kube/config"
}

# Unused by this bare stack, but declared so tasks that pin NAMESPACE (for
# prompt/fixture consistency) don't trip an "undeclared variable" warning when
# the provider resolver forwards namespace= to every GCP stack.
variable "namespace" {
  type    = string
  default = "default"
}
