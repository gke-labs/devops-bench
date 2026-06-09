terraform {
  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.15.0"
    }
  }
}

resource "helm_release" "workloads" {
  name             = "cp-recovery-workloads"
  chart            = "${path.module}/cp-recovery-chart"
  namespace        = var.namespace
  create_namespace = true

  set {
    name  = "projectID"
    value = var.project_id
  }

  set {
    name  = "namespace"
    value = var.namespace
  }

  set {
    name  = "cpRecoverySAEmail"
    value = var.cp_recovery_sa_email
  }

  set {
    name  = "etcdBackupBucket"
    value = var.etcd_backup_bucket
  }
}
