import os
import subprocess
from typing import Dict, Any
from deployers.base import Deployer

class GCPDeployer(Deployer):
    """
    GCP implementation of the Deployer interface using kubetest2 gke.
    """
    def __init__(self, project: str, zone: str, cluster_name: str, **config):
        self.project = project
        self.zone = zone
        self.cluster_name = cluster_name
        self.config = config
        # Derived relative to this file's location
        # This file is at deployers/gcp/gcp_deployer.py
        # Project root is 2 levels up.
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.bin_dir = os.path.abspath(os.path.join(current_dir, '..', '..', 'third_party', 'kubetest2', 'bin'))
        
    def _get_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        # Ensure kubetest2 and its plugins are in PATH
        env["PATH"] = f"{self.bin_dir}:{env.get('PATH', '')}"
        return env

    def up(self) -> None:
        cmd = [
            "kubetest2", "gke",
            "--project", self.project,
            "--zone", self.zone,
            "--cluster-name", self.cluster_name,
        ]
        for key, value in self.config.items():
            if value is not None:
                flag_name = f"--{key.replace('_', '-')}"
                cmd.extend([flag_name, str(value)])
            
        cmd.append("--up")
        print(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd, env=self._get_env(), check=True)

    def down(self) -> None:
        cmd = [
            "kubetest2", "gke",
            "--project", self.project,
            "--zone", self.zone,
            "--cluster-name", self.cluster_name,
            "--down"
        ]
        print(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd, env=self._get_env(), check=True)

    def get_cluster_info(self) -> Dict[str, Any]:
        kubeconfig_path = os.path.expanduser("~/.kube/config")
        return {
            "name": self.cluster_name,
            "zone": self.zone,
            "project": self.project,
            "kubeconfig_path": kubeconfig_path
        }
