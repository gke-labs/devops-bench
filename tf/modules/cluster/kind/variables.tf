# Copyright 2026 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

variable "cluster_name" {
  type        = string
  description = "The name of the KinD cluster"
}

variable "kubeconfig_path" {
  type        = string
  description = "Path to write the kubeconfig file"
  default     = "~/.kube/config"
}

variable "node_image" {
  type        = string
  description = "The kind node image to use"
  default     = "kindest/node:v1.29.2"
}

variable "project_id" {
  type        = string
  description = "The GCP project ID (or local-kind)"
  default     = "local-kind"
}

variable "location" {
  type        = string
  description = "The cluster location (or local)"
  default     = "local"
}

variable "node_count" {
  type        = number
  description = "Number of nodes (1 control-plane + worker nodes)"
  default     = 3
}

variable "disable_default_cni" {
  type        = bool
  description = "Disable kindnet and install a real NetworkPolicy-enforcing CNI instead"
  default     = false
}

variable "cni_manifest_url" {
  type        = string
  description = "Manifest URL applied when disable_default_cni is true"
  default     = "https://raw.githubusercontent.com/projectcalico/calico/v3.28.0/manifests/calico.yaml"
}

variable "cni_wait_timeout" {
  type        = string
  description = "Timeout for the replacement CNI's rollout and node-Ready wait, when disable_default_cni is true"
  default     = "180s"
}
