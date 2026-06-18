# The harness reads `cluster_name` + `cluster_location` and runs
# `gcloud container clusters get-credentials` for that single cluster. We return the
# PRIMARY (east) cluster here; the setup script additionally merges the WEST context
# into the kubeconfig (as `east`/`west`) so the agent has both regions available.
output "cluster_name" {
  value = module.east.cluster_name
}

output "cluster_location" {
  value = module.east.cluster_location
}

output "west_cluster_name" {
  value = module.west.cluster_name
}

output "west_cluster_location" {
  value = module.west.cluster_location
}

# Global anycast IP that fronts the storefront. Users hit this; the agent discovers it
# (e.g. `gcloud compute forwarding-rules list`) and re-points the URL map behind it.
output "lb_ip" {
  value = google_compute_global_address.lb_ip.address
}

output "primary_static_ip" {
  value = google_compute_address.east_ip.address
}

output "standby_static_ip" {
  value = google_compute_address.west_ip.address
}

output "sql_primary_instance" {
  value = google_sql_database_instance.primary.name
}

output "sql_replica_instance" {
  value = google_sql_database_instance.replica.name
}
