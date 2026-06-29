output "cluster_name" {
  value = kind_cluster.default.name
}

output "cluster_location" {
  value = "local"
}

output "kubeconfig_path" {
  value = kind_cluster.default.kubeconfig_path
}
