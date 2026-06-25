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
  }
}

provider "google" {
  project = var.project_id
  zone    = var.location
}

# GKE cluster. cluster_name is run-token-prefixed by the harness under parallel
# runs, so every concurrent run gets its own cluster — all in-cluster objects
# below are therefore collision-free without any name suffixing.
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

# Pre-seeded target workload the agent must optimize. It is deliberately
# misconfigured for autoscaling: NO resource requests/limits and NO HPA. The
# task asks the agent to add requests/limits, create an HPA (minReplicas > 1),
# and survive a load spike. The app + service are named
# ${var.target_deployment_name} so the prompt / chaos service_url /
# verification placeholders resolve to it:
#   http://{{TARGET_DEPLOYMENT_NAME}}.{{NAMESPACE}}.svc.cluster.local
#
# Image: registry.k8s.io/hpa-example — the canonical CPU-burn app from the
# Kubernetes HPA walkthrough; each HTTP request consumes CPU, so generated load
# drives CPU up and a correctly-configured HPA scales out.
resource "kubernetes_deployment_v1" "target" {
  metadata {
    name      = var.target_deployment_name
    namespace = var.namespace
    labels = {
      app = var.target_deployment_name
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = var.target_deployment_name
      }
    }

    template {
      metadata {
        labels = {
          app = var.target_deployment_name
        }
      }

      spec {
        container {
          name  = "web"
          image = "python:3.11-slim"

          # CPU-burn HTTP server on port 8080. The chaos harness port-forwards
          # `deployment/<target>` to a FIXED remote port 8080
          # (devops_bench/chaos/faults/generate_load.py:_LOCAL_PORT, passed as
          # remote_port), so the workload MUST listen on 8080 or the generated
          # load never reaches it. (registry.k8s.io/hpa-example listens on :80 and
          # would silently drop the spike — the run only "passes" because the
          # agent's HPA minReplicas scales it independent of load.)
          command = ["python3", "-c"]
          args = [
            <<-PY
              import http.server, socketserver
              class Handler(http.server.BaseHTTPRequestHandler):
                  def do_GET(self):
                      total = 0
                      for i in range(3_000_000):
                          total += i * i
                      self.send_response(200)
                      self.end_headers()
                      self.wfile.write(b"ok\n")
                  def log_message(self, *a):
                      pass
              class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
                  allow_reuse_address = True
                  daemon_threads = True
              Server(("", 8080), Handler).serve_forever()
            PY
          ]

          port {
            container_port = 8080
          }
          # No resources block on purpose: adding requests/limits is the agent's
          # job. Resource-based HPA cannot target CPU without requests set.
        }
      }
    }
  }

  # The HPA the agent creates changes the replica count; ignore it so any
  # re-apply does not fight the agent's autoscaling.
  lifecycle {
    ignore_changes = [
      spec[0].replicas,
    ]
  }
}

resource "kubernetes_service_v1" "target" {
  metadata {
    name      = var.target_deployment_name
    namespace = var.namespace
  }

  spec {
    selector = {
      app = var.target_deployment_name
    }

    port {
      port        = 8080
      target_port = 8080
    }

    type = "ClusterIP"
  }
}

output "cluster_name" {
  value = module.gke.cluster_name
}

output "cluster_location" {
  value = module.gke.cluster_location
}
