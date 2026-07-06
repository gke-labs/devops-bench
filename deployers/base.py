from abc import ABC, abstractmethod
from typing import Any


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
    def get_cluster_info(self) -> dict[str, Any]:
        """
        Returns a dictionary with cluster details.
        Expected keys: 'name', 'location', 'project', 'kubeconfig_path'
        """
        pass
