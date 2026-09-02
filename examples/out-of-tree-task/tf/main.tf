# A self-contained OpenTofu stack that lives OUTSIDE the devops-bench repo.
#
# Self-contained is the important part. The in-repo stacks under `tf/prebuilt/`
# pull in shared modules with relative paths (`source = "../../modules/cluster"`
# in tf/prebuilt/minimum/main.tf), and those paths do not resolve once the stack
# is somewhere else. An external stack must either declare its resources inline
# — as this one does — or reference the shared modules over git:
#
#   module "cluster" {
#     source = "git::https://github.com/gke-labs/devops-bench.git//tf/modules/cluster?ref=main"
#     ...
#   }

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    kind = {
      source  = "tehcyx/kind"
      version = ">= 0.5.0"
    }
  }
}

provider "kind" {}

resource "kind_cluster" "default" {
  name            = var.cluster_name
  wait_for_ready  = true
  kubeconfig_path = pathexpand(var.kubeconfig_path)
}

# The two outputs below are a HARD CONTRACT. `TFDeployer.get_cluster_info()`
# (devops_bench/deployers/tofu.py) reads exactly these names and raises a
# ConfigError if either is missing or empty. Note the second is
# `cluster_location`, not `location`.
output "cluster_name" {
  value = kind_cluster.default.name
}

output "cluster_location" {
  value = "local"
}
