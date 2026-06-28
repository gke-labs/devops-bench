from pathlib import Path
import subprocess
import json
import os
import shutil
from typing import Dict, Any
from deployers.base import Deployer


def _isolated_work_dir(stack_dir: str, tf_root: Path) -> str:
    """Return a per-run private copy of the stack dir, or ``stack_dir`` unchanged.

    Mirrors ``devops_bench/deployers/tofu.py``: per-run isolation already keys
    ``TF_DATA_DIR`` and the state file per run, but both arms still ran ``tofu``
    in the *shared* ``tf/prebuilt/<stack>`` directory, so concurrent runs of the
    SAME stack contend on its ``.terraform.lock.hcl`` (none is committed, so each
    ``init`` rewrites it). Copy the WHOLE ``tf/`` tree (stacks use relative
    ``../../`` module sources, so a leaf-only copy would break) into the run's
    scratch dir (the parent of ``TF_DATA_DIR``) and run tofu in the copied stack.
    In-repo + isolated (parallel) runs only; external/absolute stacks and single
    runs keep the original dir, and any copy failure falls back to it.
    """
    tf_data_dir = os.environ.get("TF_DATA_DIR", "").strip()
    if not tf_data_dir:
        return stack_dir
    try:
        rel = Path(stack_dir).resolve().relative_to(Path(tf_root).resolve())
    except ValueError:
        return stack_dir  # external/absolute stack: cannot relocate safely
    try:
        run_dir = Path(tf_data_dir).resolve().parent
        dest_tf = run_dir / "tf"
        shutil.copytree(tf_root, dest_tf, dirs_exist_ok=True)
        return str(dest_tf / rel)
    except OSError as exc:
        print(f"Warning: could not isolate tofu stack dir ({exc}); using shared {stack_dir}")
        return stack_dir


class TFDeployer(Deployer):
    """
    TF implementation of the Deployer interface.

    Supports the standard TF_DATA_DIR environment variable for controlling
    where OpenTofu stores its state, enabling idempotent runs.
    """
    def __init__(self, tf_dir: str, variables: Dict[str, Any] = None):
        # Locate project root (3 levels up from this file)
        repo_root = Path(__file__).resolve().parents[2]

        tf_path = Path(tf_dir)
        if tf_path.is_absolute():
            if tf_path.exists():
                self.tf_dir = str(tf_path)
            else:
                raise ValueError(f"Absolute TF directory not found: {tf_dir}")
        else:
            repo_tf_path = repo_root / "tf" / tf_path
            if repo_tf_path.exists():
                self.tf_dir = str(repo_tf_path)
            else:
                raise ValueError(
                    f"TF stack not found in repo: {tf_dir} "
                    f"(checked {repo_tf_path})"
                )

        # Per-run private working directory (a copy of the tf/ tree under the
        # run's scratch dir) when isolated; otherwise the shared stack dir.
        self.work_dir = _isolated_work_dir(self.tf_dir, repo_root / "tf")

        self.variables = variables or {}

    @staticmethod
    def _state_flags() -> list:
        """Return ``-state`` flags placing per-run state beside ``TF_DATA_DIR``.

        When ``TF_DATA_DIR`` is set (the parallel-isolation path keys it to a
        per-run ``<run>/tf-data`` dir), the local state file is written to
        ``<run>/terraform.tfstate`` — the *parent* of ``TF_DATA_DIR``, NOT
        inside it. ``<TF_DATA_DIR>/terraform.tfstate`` is OpenTofu's reserved
        backend-state path; writing the resource state there makes a later
        ``tofu init``/``output`` fail with "does not support state version 4".
        Empty when ``TF_DATA_DIR`` is unset (default in-dir state).
        """
        tf_data_dir = os.environ.get("TF_DATA_DIR", "").strip()
        if not tf_data_dir:
            return []
        return ["-state", str(Path(tf_data_dir).resolve().parent / "terraform.tfstate")]

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
        tf_path = Path(self.work_dir)
        if not tf_path.exists():
            raise ValueError(f"TF directory not found: {self.work_dir}")

        self._run_cmd(["tofu", "init", "-input=false"], cwd=self.work_dir)

        cmd = ["tofu", "apply", "-auto-approve", "-input=false", *self._state_flags()]
        for k, v in self.variables.items():
            cmd.extend(["-var", f"{k}={v}"])

        self._run_cmd(cmd, cwd=self.work_dir)


    def down(self) -> None:
        tf_path = Path(self.work_dir)
        if not tf_path.exists():
            print(
                f"Warning: TF directory {self.work_dir} not found. "
                "Skipping teardown."
            )
            return

        self._run_cmd(["tofu", "init", "-input=false"], cwd=self.work_dir)

        cmd = ["tofu", "destroy", "-auto-approve", "-input=false", *self._state_flags()]
        for k, v in self.variables.items():
            cmd.extend(["-var", f"{k}={v}"])

        self._run_cmd(cmd, cwd=self.work_dir)

    def get_cluster_info(self) -> Dict[str, Any]:
        self._run_cmd(["tofu", "init", "-input=false"], cwd=self.work_dir)

        result = self._run_cmd(
            ["tofu", "output", "-json", *self._state_flags()],
            cwd=self.work_dir,
            capture=True,
        )
        outputs = json.loads(result.stdout)

        cluster_name = outputs.get("cluster_name", {}).get("value")
        if not cluster_name:
            raise ValueError("Failed to retrieve 'cluster_name' from TF outputs.")

        location = outputs.get("cluster_location", {}).get("value")
        if not location:
            raise ValueError(
                "Failed to retrieve 'cluster_location' from TF outputs."
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

