variable "project_id" {
  type        = string
  description = "GCP Project ID."
}

variable "zone" {
  type        = string
  description = "GCE zone for the bastion VM."
  default     = "us-central1-a"
}

variable "name" {
  type        = string
  description = "Name of the bastion VM."
  default     = "bench-bastion"
}

variable "machine_type" {
  type        = string
  description = "Machine type for the bastion VM."
  default     = "e2-standard-4"
}

variable "sa_account_id" {
  type        = string
  description = "Account id for the bastion service account (see module docs)."
  default     = "openclaw-vm-sa"
}

variable "assign_external_ip" {
  type        = bool
  description = "Attach an ephemeral external IP for egress (SSH stays IAP-only)."
  default     = true
}
