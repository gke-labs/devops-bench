import pytest
from unittest.mock import patch, MagicMock
import os
import sys
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from deployers.factory import get_deployer
from deployers.gcp.gcp_deployer import GCPDeployer
from deployers.terraform.tf_deployer import TerraformDeployer


@pytest.fixture
def base_config():
    return {
        "project_id": "test-project",
        "cluster_name": "test-cluster",
        "location": "us-central1-a"
    }


@patch('deployers.terraform.tf_deployer.Path.exists', return_value=True)
def test_get_deployer_default(mock_exists, base_config):
    infra_config = {}
    deployer = get_deployer(
        infra_config,
        base_config["project_id"],
        base_config["cluster_name"],
        base_config["location"]
    )
    assert isinstance(deployer, TerraformDeployer)
    expected_stack_path = str(project_root / "terraform" / "prebuilt/kind")
    assert deployer.tf_dir == expected_stack_path


def test_get_deployer_kubetest2(base_config):
    infra_config = {"deployer": "kubetest2"}
    deployer = get_deployer(
        infra_config,
        base_config["project_id"],
        base_config["cluster_name"],
        base_config["location"]
    )
    assert isinstance(deployer, GCPDeployer)


@patch('deployers.terraform.tf_deployer.Path.exists', return_value=True)
def test_get_deployer_terraform_default_stack(mock_exists, base_config):
    infra_config = {"deployer": "terraform"}
    deployer = get_deployer(
        infra_config,
        base_config["project_id"],
        base_config["cluster_name"],
        base_config["location"]
    )
    assert isinstance(deployer, TerraformDeployer)

    import pathlib
    expected_kubeconfig = os.environ.get("KUBECONFIG") or str(pathlib.Path("~/.kube/config").expanduser().resolve())
    expected_vars = {
        "cluster_name": base_config["cluster_name"],
        "location": "local",
        "kubeconfig_path": expected_kubeconfig
    }
    assert deployer.variables == expected_vars

    expected_stack_path = str(project_root / "terraform" / "prebuilt/kind")
    assert deployer.tf_dir == expected_stack_path


@patch('deployers.terraform.tf_deployer.Path.exists', return_value=True)
def test_get_deployer_terraform_custom_stack_and_vars(mock_exists, base_config):
    infra_config = {
        "deployer": "terraform",
        "stack": "custom/stack",
        "variables": {
            "node_count": 5,
            "machine_type": "n2-standard-4",
            "cluster_name": "custom-cluster" # Should override global
        }
    }
    deployer = get_deployer(
        infra_config,
        base_config["project_id"],
        base_config["cluster_name"],
        base_config["location"]
    )
    assert isinstance(deployer, TerraformDeployer)

    expected_vars = {
        "project_id": base_config["project_id"],
        "cluster_name": "custom-cluster",
        "location": base_config["location"],
        "node_count": 5,
        "machine_type": "n2-standard-4"
    }
    assert deployer.variables == expected_vars
    expected_stack_path = str(project_root / "terraform" / "custom/stack")
    assert deployer.tf_dir == expected_stack_path


@patch.dict(os.environ, {"GCP_LOCATION": "us-west1-b"})
def test_get_deployer_location_from_env(base_config):
    infra_config = {"deployer": "kubetest2"}
    # Pass None for global_location to trigger env lookup
    deployer = get_deployer(
        infra_config,
        base_config["project_id"],
        base_config["cluster_name"],
        global_location=None
    )
    assert deployer.zone == "us-west1-b"


@patch('deployers.terraform.tf_deployer.Path.exists', return_value=True)
def test_get_deployer_terraform_kind_stack(mock_exists, base_config):
    infra_config = {"deployer": "terraform", "stack": "prebuilt/kind"}
    deployer = get_deployer(
        infra_config,
        base_config["project_id"],
        base_config["cluster_name"],
        base_config["location"]
    )
    assert isinstance(deployer, TerraformDeployer)

    import pathlib
    expected_kubeconfig = os.environ.get("KUBECONFIG") or str(pathlib.Path("~/.kube/config").expanduser().resolve())
    expected_vars = {
        "cluster_name": base_config["cluster_name"],
        "location": "local",
        "kubeconfig_path": expected_kubeconfig
    }
    assert deployer.variables == expected_vars

    expected_stack_path = str(project_root / "terraform" / "prebuilt/kind")
    assert deployer.tf_dir == expected_stack_path
