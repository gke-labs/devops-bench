output "cluster_name" {
  value = kind_cluster.default.name
}

# "local" tells the TF deployer this is a kind cluster (skip gcloud get-credentials).
output "cluster_location" {
  value = "local"
}
