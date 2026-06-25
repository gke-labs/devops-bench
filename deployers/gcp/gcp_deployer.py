from pathlib import Path
import subprocess
import os
from typing import Dict, Any
from deployers.base import Deployer

class GCPDeployer(Deployer):
    """
    GCP implementation of the Deployer interface using kubetest2 gke.
    
    Migrated to pathlib for better cross-platform compatibility and readability.
    Supports both 'location' and 'zone' in initialization for robust API compatibility.
    """
    def __init__(self, project: str, location: str = None, cluster_name: str = None, zone: str = None, **config):
        self.project = project
        self.cluster_name = cluster_name
        self.config = config
        
        # Robust location resolution for backward compatibility
        self.location = location or zone or os.environ.get("GCP_LOCATION", "us-central1-a")
        self.zone = self.location 
        
        # This file is at deployers/gcp/gcp_deployer.py
        # Project root is 2 levels up.
        current_dir = Path(__file__).resolve().parent
        self.bin_dir = str((current_dir.parents[1] / "third_party" / "kubetest2" / "bin").resolve())
        
    def _get_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        # Ensure kubetest2 and its plugins are in PATH
        env["PATH"] = f"{self.bin_dir}:{env.get('PATH', '')}"
        return env

    def _state_marker_path(self) -> Path:
        """Path of the "did we create this cluster?" marker.

        Placed under the per-run dir (``BENCH_RUN_DIR``) when isolation is
        active so concurrent runs do not clobber each other's marker; falls back
        to ``/tmp`` for single runs.
        """
        base = os.environ.get("BENCH_RUN_DIR", "").strip() or "/tmp"
        return Path(base) / f"{self.project}-{self.location}-{self.cluster_name}_created"

    def up(self) -> None:
        # Check if cluster exists
        check_cmd = [
            "gcloud", "container", "clusters", "describe", self.cluster_name,
            "--project", self.project, "--location", self.location
        ]
        print(f"Checking if cluster exists: {' '.join(check_cmd)}")
        result = subprocess.run(check_cmd, capture_output=True, text=True)

        state_file = self._state_marker_path()
        state_file.parent.mkdir(parents=True, exist_ok=True)

        if result.returncode == 0:
            print(f"Cluster {self.cluster_name} already exists. Getting credentials.")
            get_cred_cmd = [
                "gcloud", "container", "clusters", "get-credentials", self.cluster_name, 
                "--project", self.project, "--location", self.location
            ]
            subprocess.run(get_cred_cmd, check=True)
            # Record that we didn't create it
            state_file.write_text("false")
        else:
            print(
                f"Cluster {self.cluster_name} does not exist or error checking. "
                "Creating it."
            )
            cmd = [
                "kubetest2", "gke",
                "--project", self.project,
                "--zone", self.location, # Passing resolved location to --zone flag in kubetest2
                "--cluster-name", self.cluster_name,
            ]
            for key, value in self.config.items():
                if value is not None:
                    flag_name = f"--{key.replace('_', '-')}"
                    cmd.extend([flag_name, str(value)])
                
            cmd.append("--up")
            print(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd, env=self._get_env(), check=True)
            # Record that we created it
            state_file.write_text("true")

    def down(self) -> None:
        state_file = self._state_marker_path()
        created_by_us = True
        if state_file.exists():
            created_by_us = state_file.read_text().strip() == "true"
                
        if not created_by_us:
            print(
                f"Skipping teardown for pre-existing cluster {self.cluster_name}"
            )
            return
            
        cmd = [
            "kubetest2", "gke",
            "--project", self.project,
            "--zone", self.location,
            "--cluster-name", self.cluster_name,
            "--down"
        ]
        print(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd, env=self._get_env(), check=True)

    def get_cluster_info(self) -> Dict[str, Any]:
        kubeconfig_path = os.environ.get(
            "KUBECONFIG", str(Path.home() / ".kube" / "config")
        )
        return {
            "name": self.cluster_name,
            "location": self.location,
            "zone": self.location, 
            "project": self.project,
            "kubeconfig_path": kubeconfig_path
        }
