import os
from typing import Dict, Any
from deployers.base import Deployer
from deployers.gcp.gcp_deployer import GCPDeployer
from deployers.tf.tf_deployer import TFDeployer

from deployers.gcp.variables import resolve_variables as resolve_gcp_vars
from deployers.kind.variables import resolve_variables as resolve_kind_vars

PROVIDER_RESOLVERS = {
    "gcp": resolve_gcp_vars,
    "kind": resolve_kind_vars,
}


class NoOpDeployer(Deployer):
    """Pass-through deployer for local testing without infrastructure provisioning."""

    def __init__(self, cluster_name: str, project_id: str):
        self._cluster_name = cluster_name
        self._project_id = project_id

    def up(self) -> None:
        print("[NoOpDeployer] Skipping infrastructure provisioning (deployer: noop / BENCH_NO_INFRA)")

    def down(self) -> None:
        print("[NoOpDeployer] Skipping infrastructure teardown (deployer: noop / BENCH_NO_INFRA)")

    def get_cluster_info(self) -> Dict[str, Any]:
        return {
            "name": self._cluster_name,
            "location": "local",
            "project": self._project_id,
            "kubeconfig_path": os.environ.get("KUBECONFIG", ""),
        }


def get_deployer(
    infra_config: Dict[str, Any],
    global_project_id: str,
    global_cluster_name: str,
    global_location: str = None
) -> Deployer:
    """
    Factory to instantiate the appropriate infrastructure deployer.

    Enforces GCP_LOCATION as the standard environment variable for location.
    """
    # Respect task-level deployer first, fallback to cloud_provider if it is a valid deployer, otherwise default to terraform
    cloud_provider = os.environ.get("CLOUD_PROVIDER", "").lower()
    deployer_type = infra_config.get("deployer")
    if not deployer_type:
        if cloud_provider in ["tofu", "gcp"]:
            deployer_type = cloud_provider
        else:
            deployer_type = "tofu"

    # Skip provisioning when the task declares ``deployer: noop`` (e.g.
    # manifest-generation tasks that never touch a cluster) or when
    # ``BENCH_NO_INFRA=true`` overrides any config (run against existing infra).
    # Mirrors the refactored arm (devops_bench/deployers/factory.py); without the
    # ``noop`` check a noop task would fall through to the GCPDeployer below.
    if deployer_type == "noop" or os.environ.get("BENCH_NO_INFRA", "false").lower() == "true":
        return NoOpDeployer(cluster_name=global_cluster_name, project_id=global_project_id)

    # Resolve Location with strict precedence: argument then GCP_LOCATION env var
    location = global_location or os.environ.get("GCP_LOCATION", "us-central1-a")

    if deployer_type == "tofu":
        stack = infra_config.get("stack") or "prebuilt/kind"
        variables = infra_config.get("variables", {})

        # Deduce provider from stack name or CLOUD_PROVIDER env var
        provider = cloud_provider or ("kind" if "kind" in stack else "gcp")

        # Dynamically resolve variables based on the cloud provider
        resolver = PROVIDER_RESOLVERS.get(provider)
        if resolver:
            variables = resolver(stack, variables, global_project_id, global_cluster_name, location)

        return TFDeployer(tf_dir=stack, variables=variables)

    # Fallback to legacy GCPDeployer (kubetest2)
    return GCPDeployer(
        project=global_project_id,
        location=location,
        cluster_name=global_cluster_name
    )
