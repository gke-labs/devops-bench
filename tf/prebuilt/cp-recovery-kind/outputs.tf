output "cluster_name" {
  value = kind_cluster.default.name
}

# The TF deployer treats "local" as a kind cluster (deployers/tf/tf_deployer.py),
# skipping `gcloud get-credentials` and using the local kubeconfig instead.
output "cluster_location" {
  value = "local"
}
