# The harness reads `cluster_name` + `cluster_location` and wires the per-run
# KUBECONFIG to that (primary) cluster. We return cluster-1 (the client); setup.sh
# merges cluster-2's context into the same kubeconfig so the agent has both.
output "cluster_name" {
  value = kind_cluster.c1.name
}

# "local" tells the TF deployer this is a kind cluster (skip gcloud get-credentials).
output "cluster_location" {
  value = "local"
}

output "backend_cluster_name" {
  value = kind_cluster.c2.name
}
