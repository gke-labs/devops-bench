from pathlib import Path
import subprocess
import json
import os
from typing import Dict, Any
from deployers.base import Deployer

class TerraformDeployer(Deployer):
    """
    Terraform implementation of the Deployer interface.

    Supports the standard TF_DATA_DIR environment variable for controlling
    where Terraform stores its state, enabling idempotent runs.
    """
    def __init__(self, tf_dir: str, variables: Dict[str, Any] = None):
        # Locate project root (3 levels up from this file)
        repo_root = Path(__file__).resolve().parents[2]

        tf_path = Path(tf_dir)
        if tf_path.is_absolute():
            if tf_path.exists():
                self.tf_dir = str(tf_path)
            else:
                raise ValueError(f"Absolute Terraform directory not found: {tf_dir}")
        else:
            repo_tf_path = repo_root / "terraform" / tf_path
            if repo_tf_path.exists():
                self.tf_dir = str(repo_tf_path)
            else:
                raise ValueError(
                    f"Terraform stack not found in repo: {tf_dir} "
                    f"(checked {repo_tf_path})"
                )

        self.variables = variables or {}

    def _run_cmd(
        self, cmd: list, cwd: str, capture: bool = False
    ) -> subprocess.CompletedProcess:
        print(f"Executing: {' '.join(cmd)} in {cwd}")
        env = os.environ.copy()
        if "TF_DATA_DIR" in env:
             print(f"Using TF_DATA_DIR: {env['TF_DATA_DIR']}")

        if capture:
            return subprocess.run(
                cmd, cwd=cwd, check=True, capture_output=True, text=True, env=env
            )
        else:
            return subprocess.run(cmd, cwd=cwd, check=True, env=env)

    def up(self) -> None:
        tf_path = Path(self.tf_dir)
        if not tf_path.exists():
            raise ValueError(f"Terraform directory not found: {self.tf_dir}")

        self._run_cmd(["terraform", "init", "-input=false"], cwd=self.tf_dir)

        cmd = ["terraform", "apply", "-auto-approve", "-input=false"]
        for k, v in self.variables.items():
            cmd.extend(["-var", f"{k}={v}"])

        self._run_cmd(cmd, cwd=self.tf_dir)


    def down(self) -> None:
        tf_path = Path(self.tf_dir)
        if not tf_path.exists():
            print(
                f"Warning: Terraform directory {self.tf_dir} not found. "
                "Skipping teardown."
            )
            return

        self._run_cmd(["terraform", "init", "-input=false"], cwd=self.tf_dir)

        cmd = ["terraform", "destroy", "-auto-approve", "-input=false"]
        for k, v in self.variables.items():
            cmd.extend(["-var", f"{k}={v}"])

        self._run_cmd(cmd, cwd=self.tf_dir)

    def get_cluster_info(self) -> Dict[str, Any]:
        self._run_cmd(["terraform", "init", "-input=false"], cwd=self.tf_dir)

        result = self._run_cmd(
            ["terraform", "output", "-json"], cwd=self.tf_dir, capture=True
        )
        outputs = json.loads(result.stdout)

        cluster_name = outputs.get("cluster_name", {}).get("value")
        if not cluster_name:
            raise ValueError("Failed to retrieve 'cluster_name' from Terraform outputs.")

        location = outputs.get("cluster_location", {}).get("value")
        if not location:
            raise ValueError(
                "Failed to retrieve 'cluster_location' from Terraform outputs."
            )

        kubeconfig_path = os.environ.get(
            "KUBECONFIG", str(Path.home() / ".kube" / "config")
        )

        if location == "local":
            project = self.variables.get("project_id") or os.environ.get("GCP_PROJECT_ID") or "local-kind"
            return {
                "name": cluster_name,
                "location": location,
                "project": project,
                "kubeconfig_path": kubeconfig_path
            }

        project = self.variables.get("project_id") or os.environ.get("GCP_PROJECT_ID")
        if not project:
             raise ValueError("Project ID not found in variables or environment (GCP_PROJECT_ID).")

        print(f"Configuring kubectl for cluster: {cluster_name} in {location}...")
        subprocess.run([
            "gcloud", "container", "clusters", "get-credentials", cluster_name,
            "--location", location, "--project", project
        ], check=True)

        return {
            "name": cluster_name,
            "location": location,
            "project": project,
            "kubeconfig_path": kubeconfig_path
        }

