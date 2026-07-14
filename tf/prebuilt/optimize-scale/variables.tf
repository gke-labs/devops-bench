variable "infra_provider" {
  description = "The cloud provider to use (gcp or kind)"
  type        = string
}

variable "project_id" {
  description = "The GCP project ID (empty for kind)"
  type        = string
  default     = ""
}

variable "cluster_name" {
  description = "The name of the cluster (run-token-prefixed under parallel runs)"
  type        = string
}

variable "location" {
  description = "GCP zone/region or 'local'"
  type        = string
  # Empty by default so the cluster router picks the provider-appropriate value
  # (us-central1-a for GKE, "local" for KinD), matching the minimum/gpu-stress-test
  # stacks. A literal "local" here would be forwarded verbatim to the GKE module.
  default = ""
}

variable "node_count" {
  type    = number
  default = 3
}

variable "machine_type" {
  type    = string
  default = "e2-standard-2"
}


variable "node_image" {
  description = "The KinD node image to use"
  type        = string
  default     = null
}

variable "kubeconfig_path" {
  description = "The path to the local kubeconfig file"
  type        = string
  default     = "~/.kube/config"
}

variable "namespace" {
  description = "Namespace the target workload is deployed into. Must match the harness {{NAMESPACE}} placeholder. 'default' always exists; any other value must be pre-created."
  type        = string
  default     = "default"
}

variable "target_deployment_name" {
  description = "Name of the pre-seeded Deployment + Service the agent must optimize. Must match the harness {{TARGET_DEPLOYMENT_NAME}} placeholder."
  type        = string
  default     = "scale-target"
}
