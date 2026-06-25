variable "project_id" {}
variable "cluster_name" {}

variable "location" { default = "us-central1-a" }
variable "node_count" {
  type    = number
  default = 3
}
variable "machine_type" {
  type    = string
  default = "e2-standard-2"
}

# Unused by this bare stack, but declared so tasks that pin NAMESPACE (for
# prompt/fixture consistency) don't trip an "undeclared variable" warning when
# the provider resolver forwards namespace= to every GCP stack.
variable "namespace" {
  type    = string
  default = "default"
}
