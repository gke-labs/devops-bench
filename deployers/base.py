from abc import ABC, abstractmethod
from typing import Dict, Any

class Deployer(ABC):
    """
    Abstract base class for cloud-specific infra deployers.
    """

    @abstractmethod
    def up(self) -> None:
        """
        Creates the cluster.
        """
        pass

    @abstractmethod
    def down(self) -> None:
        """
        Tears down the cluster.
        """
        pass

    @abstractmethod
    def get_cluster_info(self) -> Dict[str, Any]:
        """
        Returns a dictionary with cluster details.
        Expected keys: 'name', 'zone', 'project', 'kubeconfig_path'
        """
        pass
