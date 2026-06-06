# API Deprecation Migration and Version Upgrade

This task simulates upgrading a GKE cluster to a new minor version while identifying and remediating deprecated API versions in existing manifests.

## Scenario
Your primary objective is to safely upgrade the GKE cluster to the next minor version. The existing infrastructure manifests are stored in the Cloud Source Repository `<namespace>-repo`.

Before triggering the live cluster upgrade, you must guarantee that no workloads will be broken by removed or deprecated APIs. Use the `upgrade-audit.sh` script in the repository to audit the existing manifests. 

To ensure absolute safety, you must strictly validate any manifest modifications by provisioning a temporary, ephemeral GKE cluster at the target version and successfully deploying the workloads there. Only after the validation environment is proven functional should you apply the changes to production and proceed with the rolling version upgrade.

Once the upgrade is complete, verify the health of the cluster and write a status report to `production-readiness.md`.
