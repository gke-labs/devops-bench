import os
from typing import Dict, Any
from deployers.base import Deployer
from deployers.gcp.gcp_deployer import GCPDeployer
from deployers.terraform.tf_deployer import TerraformDeployer

from deployers.gcp.variables import resolve_variables as resolve_gcp_vars
from deployers.kind.variables import resolve_variables as resolve_kind_vars

PROVIDER_RESOLVERS = {
    "gcp": resolve_gcp_vars,
    "kind": resolve_kind_vars,
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
    # Check if CLOUD_PROVIDER environment variable overrides the task-level deployer
    cloud_provider = os.environ.get("CLOUD_PROVIDER", "").lower()
    deployer_type = cloud_provider if cloud_provider else infra_config.get("deployer", "terraform")

    # Resolve Location with strict precedence: argument then GCP_LOCATION env var
    location = global_location or os.environ.get("GCP_LOCATION", "us-central1-a")

    if deployer_type == "terraform":
        stack = infra_config.get("stack") or "prebuilt/kind"
        variables = infra_config.get("variables", {})

        # Deduce provider from stack name or CLOUD_PROVIDER env var
        provider = cloud_provider or ("kind" if "kind" in stack else "gcp")

        # Dynamically resolve variables based on the cloud provider
        resolver = PROVIDER_RESOLVERS.get(provider)
        if resolver:
            variables = resolver(stack, variables, global_project_id, global_cluster_name, location)

        return TerraformDeployer(tf_dir=stack, variables=variables)

    # Fallback to legacy GCPDeployer (kubetest2)
    return GCPDeployer(
        project=global_project_id,
        location=location,
        cluster_name=global_cluster_name
    )
