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
variable "namespace" {
  type    = string
  default = "default"
}

