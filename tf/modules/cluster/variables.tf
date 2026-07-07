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

variable "gpu_type" {
  type        = string
  description = "Abstract GPU family: 'l4', 'a100', 't4', or ''"
  default     = ""
}

variable "gpu_count" {
  type        = number
  description = "Quantity of GPUs to attach per node"
  default     = 1
}

variable "project_id" {
  type        = string
  description = "GCP Project ID (GCP-only)"
  default     = ""
}

variable "kubeconfig_path" {
  type        = string
  description = "Target path to write kubeconfig (KinD-only)"
  default     = "~/.kube/config"
}

variable "kubernetes_version" {
  type        = string
  description = "The Kubernetes version for the cluster"
  default     = null
}

variable "enable_workload_identity" {
  type        = bool
  description = "Enable GKE Workload Identity (GCP-only)"
  default     = false
}

variable "agent_service_account" {
  type        = string
  description = "The service account email of the agent (GCP-only)"
  default     = ""
}

variable "enable_iap_ssh" {
  type        = bool
  description = "Enable IAP SSH firewall rule (GCP-only)"
  default     = false
}

variable "node_image" {
  type        = string
  description = "The kind node image to use (KinD-only)"
  default     = "kindest/node:v1.29.2"
}

