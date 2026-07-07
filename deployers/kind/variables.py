import os
import pathlib
from typing import Any, Dict

def resolve_variables(
    stack: str,
    custom_variables: Dict[str, Any],
    global_project_id: str,
    global_cluster_name: str,
    global_location: str
) -> Dict[str, Any]:
    """Resolves default variables for local KinD-based stacks."""
    variables = custom_variables.copy()
    cluster_name = global_cluster_name or "devops-bench-kind"
    variables.setdefault("cluster_name", cluster_name)
    variables.setdefault("location", "local")

    kubeconfig_path = os.environ.get("KUBECONFIG") or str(
        pathlib.Path("~/.kube/config").expanduser().resolve()
    )
    variables.setdefault("kubeconfig_path", kubeconfig_path)
    return variables
