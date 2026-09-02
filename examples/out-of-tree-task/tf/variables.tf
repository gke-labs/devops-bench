# Declare every variable the harness may inject, even the ones this stack
# ignores. `TFDeployer` filters `-var` flags against the variables a stack
# actually declares (devops_bench/deployers/tofu.py `_var_flags`), so an
# undeclared variable is silently DROPPED rather than passed through — the stack
# then falls back to its own default and you get a cluster with the wrong name.
#
# The provider decides what gets injected: see `resolve_variables()` in
# devops_bench/providers/kind.py (kind) or gcp.py (GCP).

variable "cluster_name" {
  type        = string
  description = "Run-unique cluster name, injected by the harness."
  default     = "devops-bench-oot"
}

variable "location" {
  type        = string
  description = "Region/zone (GCP) or 'local' (kind)."
  default     = "local"
}

variable "kubeconfig_path" {
  type        = string
  description = "Where to write the kubeconfig."
  default     = "~/.kube/config"
}

# Injected by both providers. Unused by this kind stack, but declared so they
# are not dropped with a warning in the run log.
variable "infra_provider" {
  type        = string
  description = "Target infra provider (gcp, kind)."
  default     = "kind"
}

variable "project_id" {
  type        = string
  description = "GCP project ID; 'local' under the kind provider."
  default     = ""
}
