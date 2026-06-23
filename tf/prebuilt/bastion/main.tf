# Concrete stack that provisions a static eval-harness bastion.
#
#   cd tf/prebuilt/bastion && tofu init && tofu apply -var project_id=<proj>
#
# See docs/bastion.md for the full workflow.

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
  }
}

provider "google" {
  project = var.project_id
  zone    = var.zone
}

module "bastion" {
  source = "../../modules/bastion"

  project_id         = var.project_id
  zone               = var.zone
  name               = var.name
  machine_type       = var.machine_type
  sa_account_id      = var.sa_account_id
  assign_external_ip = var.assign_external_ip

  # This batteries-included consumer opts the bastion SA into the roles the
  # secret-rotation stack provisions with. The reusable module itself defaults
  # to [] (least privilege); the broad grant lives here, not in the module.
  sa_roles = [
    "roles/editor",
    "roles/resourcemanager.projectIamAdmin",
    "roles/iam.serviceAccountAdmin",
  ]
}

output "sa_email" {
  description = "Email of the service account the bastion runs as."
  value       = module.bastion.sa_email
}

output "iap_ssh_command" {
  description = "Command to SSH into the bastion over IAP."
  value       = module.bastion.iap_ssh_command
}
