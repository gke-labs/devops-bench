terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.0.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0.0"
    }
  }
}

provider "google" {
  project = var.project_id
  zone    = var.location
}

locals {
  # Per-run GitOps repo path. All runs share the bastion host and this dir is
  # NOT under the per-run scratch dir, so a fixed path would let one run's
  # destroy-time ``rm -rf`` wipe a concurrent run's repo. cluster_name is
  # run-token-prefixed, so this is unique per run. The task prompt references the
  # same path via the {{GKE_CLUSTER_NAME}} placeholder.
  gitops_repo_path = "/app/results/gitops-repo-${var.cluster_name}"
}

module "gke" {
  source       = "../../modules/gke"
  project_id   = var.project_id
  cluster_name = var.cluster_name
  location     = var.location
  node_count   = var.node_count
  machine_type = var.machine_type
}

data "google_client_config" "default" {}

provider "kubernetes" {
  host                   = "https://${module.gke.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(module.gke.cluster_ca_certificate)
}

resource "kubernetes_namespace" "gitops" {
  count = var.namespace == "default" ? 0 : 1
  metadata {
    name = var.namespace
  }
}

resource "kubernetes_deployment" "hello_app" {
  metadata {
    name      = "hello-app"
    namespace = var.namespace
    labels = {
      app = "hello-app"
    }
  }

  spec {
    replicas = 2

    selector {
      match_labels = {
        app = "hello-app"
      }
    }

    template {
      metadata {
        labels = {
          app = "hello-app"
        }
      }

      spec {
        container {
          image = "us-docker.pkg.dev/google-samples/containers/gke/hello-app:2.0-broken"
          name  = "hello-app"
          port {
            container_port = 8080
          }
        }
      }
    }
  }

  depends_on = [module.gke, kubernetes_namespace.gitops]
}

resource "null_resource" "gitops_repo_setup" {
  # Exposed to the destroy-time provisioner, which may only reference ``self``.
  triggers = {
    repo_path = local.gitops_repo_path
  }

  provisioner "local-exec" {
    command = <<EOT
      mkdir -p ${local.gitops_repo_path}
      cd ${local.gitops_repo_path}
      git init
      git config user.email "gitops-bot@example.com"
      git config user.name "GitOps Bot"
      
      # Write working deployment
      cat <<EOF > deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hello-app
  namespace: ${var.namespace}
spec:
  replicas: 2
  selector:
    matchLabels:
      app: hello-app
  template:
    metadata:
      labels:
        app: hello-app
    spec:
      containers:
      - name: hello-app
        image: us-docker.pkg.dev/google-samples/containers/gke/hello-app:1.0
        ports:
        - containerPort: 8080
EOF
      git add deployment.yaml
      git commit -m "Deploy hello-app v1.0"
      
      # Write broken deployment
      cat <<EOF > deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hello-app
  namespace: ${var.namespace}
spec:
  replicas: 2
  selector:
    matchLabels:
      app: hello-app
  template:
    metadata:
      labels:
        app: hello-app
    spec:
      containers:
      - name: hello-app
        image: us-docker.pkg.dev/google-samples/containers/gke/hello-app:2.0-broken
        ports:
        - containerPort: 8080
EOF
      git add deployment.yaml
      git commit -m "Upgrade hello-app to v2.0-broken"
    EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = "rm -rf ${self.triggers.repo_path}"
  }
}

output "cluster_name" {
  value = module.gke.cluster_name
}

output "cluster_location" {
  value = module.gke.cluster_location
}
