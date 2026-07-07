import os
import pathlib
from typing import Any


def resolve_variables(
    stack: str,
    custom_variables: dict[str, Any],
    global_project_id: str,
    global_cluster_name: str,
    global_location: str,
) -> dict[str, Any]:
    """Resolves default variables for local KinD-based stacks."""
    variables = custom_variables.copy()
    variables.setdefault("infra_provider", "kind")
    cluster_name = global_cluster_name or "devops-bench-kind"
    variables.setdefault("cluster_name", cluster_name)
    variables.setdefault("location", "local")

    kubeconfig_path = os.environ.get("KUBECONFIG") or str(
        pathlib.Path("~/.kube/config").expanduser().resolve()
    )
    variables.setdefault("kubeconfig_path", kubeconfig_path)
    return variables
