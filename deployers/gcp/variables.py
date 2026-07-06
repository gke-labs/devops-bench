import os
from typing import Any


def resolve_variables(
    stack: str,
    custom_variables: dict[str, Any],
    global_project_id: str,
    global_cluster_name: str,
    global_location: str,
) -> dict[str, Any]:
    """Resolves default variables for GCP-based TF stacks."""
    variables = custom_variables.copy()
    variables.setdefault("project_id", global_project_id)
    variables.setdefault("cluster_name", global_cluster_name)
    variables.setdefault("location", global_location)
    if "NAMESPACE" in os.environ:
        variables.setdefault("namespace", os.environ["NAMESPACE"])
    return variables
