# b-0033 -- cluster outputs.
#
# The harness reads exactly these two names back out of `tofu output -json` and
# raises ConfigError if either is missing. Do not rename them.
output "cluster_name" {
  value       = module.cluster.cluster_name
  description = "The finalized name of the created cluster"
}

output "cluster_location" {
  value       = module.cluster.location
  description = "The region/zone or 'local'"
}
