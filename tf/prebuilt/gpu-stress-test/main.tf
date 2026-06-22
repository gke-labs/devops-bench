terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.location
}

resource "google_service_account" "gke_nodes" {
  account_id   = "gke-nodes-st-${trim(substr(var.cluster_name, 0, 10), "-")}"
  display_name = "GKE Node Service Account for Stress Test ${var.cluster_name}"
}

resource "google_project_iam_member" "gke_nodes_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_monitoring_viewer" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_metadata_writer" {
  project = var.project_id
  role    = "roles/stackdriver.resourceMetadata.writer"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_artifact_registry_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_container_cluster" "primary" {
  name                     = var.cluster_name
  location                 = var.location
  remove_default_node_pool = true
  initial_node_count       = 1
  deletion_protection      = false

  ip_allocation_policy {}
}

resource "google_container_node_pool" "primary_nodes" {
  name       = "gpu-node-pool"
  location   = var.location
  cluster    = google_container_cluster.primary.name
  node_count = var.node_count

  node_config {
    preemptible     = false
    machine_type    = var.machine_type
    service_account = google_service_account.gke_nodes.email

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    guest_accelerator {
      type  = "nvidia-l4"
      count = 1

      gpu_driver_installation_config {
        gpu_driver_version = "DEFAULT"
      }
    }
  }
}

resource "null_resource" "write_synthetic_logs" {
  provisioner "local-exec" {
    command = <<EOT
      gcloud logging write "container" "{\"message\": \"hypercomputer-agent: GCS FUSE buffer exhaustion during checkpoint load\", \"container_name\": \"hypercomputer-agent\"}" --severity=ERROR --project=${var.project_id} --payload-type=json --monitored-resource-type=k8s_container --monitored-resource-labels=project_id=${var.project_id},location=${var.location},cluster_name=${var.cluster_name},namespace_name=default,pod_name=hypercomputer-agent-deployment-xyz,container_name=hypercomputer-agent
      gcloud logging write "container" "{\"message\": \"HorizontalPodAutoscaler: HPA max-replica saturation for deployment/hypercomputer-agent (max: 10)\", \"container_name\": \"hpa-controller\"}" --severity=WARNING --project=${var.project_id} --payload-type=json --monitored-resource-type=k8s_container --monitored-resource-labels=project_id=${var.project_id},location=${var.location},cluster_name=${var.cluster_name},namespace_name=default,pod_name=hpa-controller-xyz,container_name=hpa-controller
    EOT
  }

  depends_on = [
    google_container_cluster.primary,
    google_container_node_pool.primary_nodes
  ]
}

output "cluster_name" {
  value = google_container_cluster.primary.name
}

output "cluster_location" {
  value = google_container_cluster.primary.location
}
