import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is in path
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from deployers.factory import NoOpDeployer, get_deployer  # noqa: E402
from deployers.gcp.gcp_deployer import GCPDeployer  # noqa: E402
from deployers.tf.tf_deployer import TFDeployer  # noqa: E402


@pytest.fixture
def base_config():
    return {
        "project_id": "test-project",
        "cluster_name": "test-cluster",
        "location": "us-central1-a",
    }


@patch("deployers.tf.tf_deployer.Path.exists", return_value=True)
def test_get_deployer_default(mock_exists, base_config):
    infra_config = {}
    deployer = get_deployer(
        infra_config,
        base_config["project_id"],
        base_config["cluster_name"],
        base_config["location"],
    )
    assert isinstance(deployer, TFDeployer)
    expected_stack_path = str(project_root / "tf" / "prebuilt/kind")
    assert deployer.tf_dir == expected_stack_path


def test_get_deployer_kubetest2(base_config):
    infra_config = {"deployer": "kubetest2"}
    deployer = get_deployer(
        infra_config,
        base_config["project_id"],
        base_config["cluster_name"],
        base_config["location"],
    )
    assert isinstance(deployer, GCPDeployer)


@patch("deployers.tf.tf_deployer.Path.exists", return_value=True)
def test_get_deployer_tofu_default_stack(mock_exists, base_config):
    infra_config = {"deployer": "tofu"}
    deployer = get_deployer(
        infra_config,
        base_config["project_id"],
        base_config["cluster_name"],
        base_config["location"],
    )
    assert isinstance(deployer, TFDeployer)

    import pathlib

    expected_kubeconfig = os.environ.get("KUBECONFIG") or str(
        pathlib.Path("~/.kube/config").expanduser().resolve()
    )
    expected_vars = {
        "cluster_name": base_config["cluster_name"],
        "location": "local",
        "kubeconfig_path": expected_kubeconfig,
    }
    assert deployer.variables == expected_vars

    expected_stack_path = str(project_root / "tf" / "prebuilt/kind")
    assert deployer.tf_dir == expected_stack_path


@patch("deployers.tf.tf_deployer.Path.exists", return_value=True)
def test_get_deployer_tofu_custom_stack_and_vars(mock_exists, base_config):
    infra_config = {
        "deployer": "tofu",
        "stack": "custom/stack",
        "variables": {
            "node_count": 5,
            "machine_type": "n2-standard-4",
            "cluster_name": "custom-cluster",  # Should override global
        },
    }
    deployer = get_deployer(
        infra_config,
        base_config["project_id"],
        base_config["cluster_name"],
        base_config["location"],
    )
    assert isinstance(deployer, TFDeployer)

    expected_vars = {
        "project_id": base_config["project_id"],
        "cluster_name": "custom-cluster",
        "location": base_config["location"],
        "node_count": 5,
        "machine_type": "n2-standard-4",
    }
    assert deployer.variables == expected_vars
    expected_stack_path = str(project_root / "tf" / "custom/stack")
    assert deployer.tf_dir == expected_stack_path


@patch.dict(os.environ, {"GCP_LOCATION": "us-west1-b"})
def test_get_deployer_location_from_env(base_config):
    infra_config = {"deployer": "kubetest2"}
    # Pass None for global_location to trigger env lookup
    deployer = get_deployer(
        infra_config, base_config["project_id"], base_config["cluster_name"], global_location=None
    )
    assert deployer.zone == "us-west1-b"


@patch("deployers.tf.tf_deployer.Path.exists", return_value=True)
def test_get_deployer_tofu_kind_stack(mock_exists, base_config):
    infra_config = {"deployer": "tofu", "stack": "prebuilt/kind"}
    deployer = get_deployer(
        infra_config,
        base_config["project_id"],
        base_config["cluster_name"],
        base_config["location"],
    )
    assert isinstance(deployer, TFDeployer)

    import pathlib

    expected_kubeconfig = os.environ.get("KUBECONFIG") or str(
        pathlib.Path("~/.kube/config").expanduser().resolve()
    )
    expected_vars = {
        "cluster_name": base_config["cluster_name"],
        "location": "local",
        "kubeconfig_path": expected_kubeconfig,
    }
    assert deployer.variables == expected_vars

    expected_stack_path = str(project_root / "tf" / "prebuilt/kind")
    assert deployer.tf_dir == expected_stack_path


# ---------------------------------------------------------------------------
# NoOpDeployer
# ---------------------------------------------------------------------------


@patch.dict(os.environ, {"BENCH_NO_INFRA": "true"})
def test_get_deployer_no_infra_returns_noop(base_config):
    deployer = get_deployer(
        {},
        base_config["project_id"],
        base_config["cluster_name"],
    )
    assert isinstance(deployer, NoOpDeployer)


@patch.dict(os.environ, {"BENCH_NO_INFRA": "true"})
def test_no_infra_takes_precedence_over_infra_config(base_config):
    """BENCH_NO_INFRA should short-circuit even when a deployer is specified."""
    deployer = get_deployer(
        {"deployer": "tofu", "stack": "prebuilt/kind"},
        base_config["project_id"],
        base_config["cluster_name"],
    )
    assert isinstance(deployer, NoOpDeployer)


def test_noop_deployer_up_is_silent(capsys, base_config):
    d = NoOpDeployer(cluster_name="test-cluster", project_id="test-project")
    d.up()
    assert "NoOpDeployer" in capsys.readouterr().out


def test_noop_deployer_down_is_silent(capsys, base_config):
    d = NoOpDeployer(cluster_name="test-cluster", project_id="test-project")
    d.down()
    assert "NoOpDeployer" in capsys.readouterr().out


def test_noop_deployer_get_cluster_info(base_config):
    d = NoOpDeployer(cluster_name="test-cluster", project_id="test-project")
    info = d.get_cluster_info()
    assert info["name"] == "test-cluster"
    assert info["project"] == "test-project"
    assert info["location"] == "local"
