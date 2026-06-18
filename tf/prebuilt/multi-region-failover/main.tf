terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.0.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region_primary
}

locals {
  # The agent runs as this SA; the east module grants it project-wide container.admin
  # (which reaches both clusters). West passes "" so we don't create a duplicate binding.
  agent_sa = var.agent_service_account != "" ? var.agent_service_account : "openclaw-vm-sa@${var.project_id}.iam.gserviceaccount.com"

  east_cluster = "${var.cluster_name}-east"
  west_cluster = "${var.cluster_name}-west"
}

# Cloud SQL instance names cannot be reused for ~1 week after deletion, which breaks
# back-to-back eval runs. A random suffix sidesteps the collision on every apply.
resource "random_id" "suffix" {
  byte_length = 3
}

# ---------------------------------------------------------------------------
# Two regional (zonal) GKE clusters: east = primary, west = standby.
# ---------------------------------------------------------------------------
module "east" {
  source                = "../../modules/gke"
  project_id            = var.project_id
  cluster_name          = local.east_cluster
  location              = var.zone_primary
  node_count            = var.node_count_primary
  machine_type          = var.machine_type
  agent_service_account = local.agent_sa
}

module "west" {
  source       = "../../modules/gke"
  project_id   = var.project_id
  cluster_name = local.west_cluster
  location     = var.zone_standby
  node_count   = var.node_count_standby
  machine_type = var.machine_type
  # container.admin is granted project-wide by the east module; don't duplicate it.
  agent_service_account = ""
}

# ---------------------------------------------------------------------------
# Reserved external IPs. The regional IPs are assigned to each cluster's frontend
# Service (loadBalancerIP) so the global LB's internet NEGs can target known IPs.
# ---------------------------------------------------------------------------
resource "google_compute_address" "east_ip" {
  name   = "fe-east-${var.cluster_name}-${random_id.suffix.hex}"
  region = var.region_primary
}

resource "google_compute_address" "west_ip" {
  name   = "fe-west-${var.cluster_name}-${random_id.suffix.hex}"
  region = var.region_standby
}

resource "google_compute_global_address" "lb_ip" {
  name = "storefront-lb-${var.cluster_name}-${random_id.suffix.hex}"
}

# ---------------------------------------------------------------------------
# Cross-region Cloud SQL: primary in east, read replica in west. The agent checks
# replication health/lag here before deciding it is safe to fail over.
# ---------------------------------------------------------------------------
resource "google_sql_database_instance" "primary" {
  name                = "storefront-${var.cluster_name}-${random_id.suffix.hex}"
  database_version    = "MYSQL_8_0"
  region              = var.region_primary
  deletion_protection = false

  settings {
    tier              = var.db_tier
    availability_type = "ZONAL"
    backup_configuration {
      enabled            = true
      binary_log_enabled = true # required to source a read replica
    }
  }
}

resource "google_sql_database_instance" "replica" {
  name                 = "storefront-${var.cluster_name}-replica-${random_id.suffix.hex}"
  database_version     = "MYSQL_8_0"
  region               = var.region_standby
  master_instance_name = google_sql_database_instance.primary.name
  deletion_protection  = false

  replica_configuration {
    failover_target = false
  }

  settings {
    tier              = var.db_tier
    availability_type = "ZONAL"
  }

  depends_on = [google_sql_database_instance.primary]
}

resource "google_sql_database" "app" {
  name     = "storefront"
  instance = google_sql_database_instance.primary.name
}

resource "google_sql_user" "app" {
  name     = "storefront"
  instance = google_sql_database_instance.primary.name
  password = "storefront-${random_id.suffix.hex}"
}

# ---------------------------------------------------------------------------
# Global external HTTP load balancer fronting both regions via internet NEGs.
# The URL map default_service is pinned to EAST; when east goes down the agent must
# re-point it to WEST (there is no automatic cross-backend-service failover).
# ---------------------------------------------------------------------------
resource "google_compute_global_network_endpoint_group" "east" {
  name                  = "neg-east-${var.cluster_name}-${random_id.suffix.hex}"
  network_endpoint_type = "INTERNET_IP_PORT"
  default_port          = 80
}

resource "google_compute_global_network_endpoint" "east" {
  global_network_endpoint_group = google_compute_global_network_endpoint_group.east.name
  ip_address                    = google_compute_address.east_ip.address
  port                          = 80
}

resource "google_compute_global_network_endpoint_group" "west" {
  name                  = "neg-west-${var.cluster_name}-${random_id.suffix.hex}"
  network_endpoint_type = "INTERNET_IP_PORT"
  default_port          = 80
}

resource "google_compute_global_network_endpoint" "west" {
  global_network_endpoint_group = google_compute_global_network_endpoint_group.west.name
  ip_address                    = google_compute_address.west_ip.address
  port                          = 80
}

# Health checks are not supported on internet-NEG backends, so they are omitted; the
# agent detects the outage from the 5xx error rate, not from LB health state.
resource "google_compute_backend_service" "east" {
  name                  = "be-east-${var.cluster_name}-${random_id.suffix.hex}"
  protocol              = "HTTP"
  load_balancing_scheme = "EXTERNAL"
  timeout_sec           = 10

  backend {
    group = google_compute_global_network_endpoint_group.east.id
  }
}

resource "google_compute_backend_service" "west" {
  name                  = "be-west-${var.cluster_name}-${random_id.suffix.hex}"
  protocol              = "HTTP"
  load_balancing_scheme = "EXTERNAL"
  timeout_sec           = 10

  backend {
    group = google_compute_global_network_endpoint_group.west.id
  }
}

resource "google_compute_url_map" "lb" {
  name = "storefront-urlmap-${var.cluster_name}-${random_id.suffix.hex}"
  # Pinned to the primary region. The agent's failover action is to set this to the
  # west backend service (e.g. `gcloud compute url-maps set-default-service`).
  default_service = google_compute_backend_service.east.id
}

resource "google_compute_target_http_proxy" "lb" {
  name    = "storefront-proxy-${var.cluster_name}-${random_id.suffix.hex}"
  url_map = google_compute_url_map.lb.id
}

resource "google_compute_global_forwarding_rule" "lb" {
  name                  = "storefront-fr-${var.cluster_name}-${random_id.suffix.hex}"
  target                = google_compute_target_http_proxy.lb.id
  ip_address            = google_compute_global_address.lb_ip.address
  port_range            = "80"
  load_balancing_scheme = "EXTERNAL"
}

# ---------------------------------------------------------------------------
# Outside-the-cluster setup: deploy the app to both clusters, inject the regional
# outage in east, leave west missing the replicated config, seed the GitOps repo.
# ---------------------------------------------------------------------------
resource "null_resource" "setup" {
  triggers = {
    east_cluster = module.east.cluster_name
    west_cluster = module.west.cluster_name
    east_ip      = google_compute_address.east_ip.address
    west_ip      = google_compute_address.west_ip.address
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = "${path.module}/scripts/setup.sh"

    environment = {
      PROJECT_ID    = var.project_id
      NAMESPACE     = var.namespace
      EAST_CLUSTER  = module.east.cluster_name
      EAST_ZONE     = var.zone_primary
      WEST_CLUSTER  = module.west.cluster_name
      WEST_ZONE     = var.zone_standby
      EAST_IP       = google_compute_address.east_ip.address
      WEST_IP       = google_compute_address.west_ip.address
      LB_IP         = google_compute_global_address.lb_ip.address
      REPO_PATH     = var.repo_path
      SQL_PRIMARY   = google_sql_database_instance.primary.name
      SQL_REPLICA   = google_sql_database_instance.replica.name
      MANIFESTS_DIR = "${path.module}/manifests"
    }
  }

  depends_on = [
    module.east,
    module.west,
    google_sql_database_instance.replica,
    google_compute_global_forwarding_rule.lb,
  ]
}
