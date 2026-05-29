import os
from typing import Dict, Any
from deployers.base import Deployer
from deployers.gcp.gcp_deployer import GCPDeployer
from deployers.terraform.tf_deployer import TerraformDeployer

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
    deployer_type = infra_config.get("deployer", "kubetest2")

    # Resolve Location with strict precedence: argument then GCP_LOCATION env var
    location = global_location or os.environ.get("GCP_LOCATION", "us-central1-a")

    if deployer_type == "terraform":

        stack = infra_config.get("stack") or "prebuilt/minimum"
        variables = infra_config.get("variables", {})

        # Ensure critical variables are present, defaulting to globals
        variables.setdefault("project_id", global_project_id)
        variables.setdefault("cluster_name", global_cluster_name)
        variables.setdefault("location", location)

        return TerraformDeployer(tf_dir=stack, variables=variables)

    # Fallback to legacy GCPDeployer (kubetest2)
    return GCPDeployer(
        project=global_project_id,
        location=location,

        cluster_name=global_cluster_name
    )
