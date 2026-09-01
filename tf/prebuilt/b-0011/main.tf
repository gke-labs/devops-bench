terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 7.45.0"
    }
    kind = {
      source  = "tehcyx/kind"
      version = "= 0.11.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "= 3.3.1"
    }
  }
}

provider "google" {
  project = var.project_id != "" ? var.project_id : null
  region  = var.location != "" && var.location != "local" ? var.location : null
}

provider "kind" {}

# b-0011: The rollback that would make everything worse: checkout's stuck instance count and the request inflated two revisions back. The seed manifests
# (manifests/00-gating.yaml, manifests/10-workloads.yaml) and the workload
# they seed are applied by setup.sh.
module "cluster" {
  source          = "../../modules/cluster"
  infra_provider  = var.infra_provider
  project_id      = var.project_id
  cluster_name    = var.cluster_name
  location        = var.location
  node_count      = var.node_count
  machine_type    = var.machine_type
  kubeconfig_path = var.kubeconfig_path
}

# Outside-the-cluster setup for b-0011: apply the seed manifests in
# gating-then-rest order (see manifests/00-gating.yaml, manifests/10-workloads.yaml)
# and assert the seeded condition(s) actually hold before the agent starts. Runs
# during `tofu apply`, before the agent starts.
resource "null_resource" "setup" {
  depends_on = [module.cluster]

  triggers = {
    cluster = module.cluster.cluster_name
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = "${path.module}/scripts/setup.sh"
    environment = {
      INFRA_PROVIDER = var.infra_provider
      PROJECT_ID     = var.project_id
      CLUSTER_NAME   = module.cluster.cluster_name
      LOCATION       = var.location
      KUBECONFIG     = pathexpand(var.kubeconfig_path)
      MANIFESTS_DIR  = "${path.module}/manifests"
      WAIT_TIMEOUT   = var.wait_timeout
    }
  }
}
