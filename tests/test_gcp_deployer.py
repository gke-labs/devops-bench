import pytest
from unittest.mock import patch, MagicMock
import os
import sys
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from deployers.gcp.gcp_deployer import GCPDeployer


@pytest.fixture(autouse=True)
def _clear_isolation_env(monkeypatch):
    """Keep the marker path under /tmp for default tests by clearing the
    per-run dir env that the parallel-isolation path would otherwise use."""
    monkeypatch.delenv("BENCH_RUN_DIR", raising=False)


@pytest.fixture
def gcp_deployer_setup():
    project = "test-project"
    location = "us-central1-a"
    cluster_name = "test-cluster"
    return {
        "project": project,
        "location": location,
        "cluster_name": cluster_name,
        "deployer": GCPDeployer(project, location, cluster_name)
    }


@patch('subprocess.run')
# Patch Path.write_text to avoid actually writing to /tmp during tests
@patch.object(Path, 'write_text')
def test_up(mock_write_text, mock_run, gcp_deployer_setup):
    deployer = gcp_deployer_setup["deployer"]

    mock_desc_process = MagicMock()
    mock_desc_process.returncode = 1

    mock_run.side_effect = [
        mock_desc_process, # describe
        MagicMock() # kubetest2
    ]

    deployer.up()

    args_list = mock_run.call_args_list
    assert len(args_list) == 2

    assert args_list[0][0][0] == [
        "gcloud", "container", "clusters", "describe",
        gcp_deployer_setup["cluster_name"],
        "--project", gcp_deployer_setup["project"],
        "--location", gcp_deployer_setup["location"]
    ]

    cmd = args_list[1][0][0]
    assert "kubetest2" in cmd
    assert "gke" in cmd
    assert "--up" in cmd
    assert gcp_deployer_setup["project"] in cmd

    env = args_list[1][1].get('env')
    assert env is not None
    assert deployer.bin_dir in env['PATH']
    mock_write_text.assert_called_once_with("true")


@patch('subprocess.run')
@patch.object(Path, 'write_text')
def test_up_with_config(mock_write_text, mock_run, gcp_deployer_setup):
    deployer = GCPDeployer(
        gcp_deployer_setup["project"],
        gcp_deployer_setup["location"],
        gcp_deployer_setup["cluster_name"],
        machine_type="n1-standard-4",
        num_nodes=5
    )

    mock_desc_process = MagicMock()
    mock_desc_process.returncode = 1

    mock_run.side_effect = [
        mock_desc_process, # describe
        MagicMock() # kubetest2
    ]

    deployer.up()

    args_list = mock_run.call_args_list
    assert len(args_list) == 2

    cmd = args_list[1][0][0]
    assert "--machine-type" in cmd
    assert "n1-standard-4" in cmd
    assert "--num-nodes" in cmd
    assert "5" in cmd
    mock_write_text.assert_called_once_with("true")


@patch('subprocess.run')
def test_down(mock_run, gcp_deployer_setup):
    deployer = gcp_deployer_setup["deployer"]

    with patch.object(Path, 'exists', return_value=True):
        with patch.object(Path, 'read_text', return_value="true"):
            deployer.down()

            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            cmd = args[0]
            assert "kubetest2" in cmd
            assert "gke" in cmd
            assert "--down" in cmd
            assert gcp_deployer_setup["project"] in cmd

            env = kwargs.get('env')
            assert env is not None
            assert deployer.bin_dir in env['PATH']


def test_state_marker_defaults_to_tmp(gcp_deployer_setup):
    deployer = gcp_deployer_setup["deployer"]
    marker = deployer._state_marker_path()
    assert marker == Path("/tmp/test-project-us-central1-a-test-cluster_created")


def test_state_marker_honors_per_run_dir(gcp_deployer_setup, monkeypatch, tmp_path):
    monkeypatch.setenv("BENCH_RUN_DIR", str(tmp_path))
    deployer = gcp_deployer_setup["deployer"]
    marker = deployer._state_marker_path()
    assert marker.parent == tmp_path
    assert marker.name == "test-project-us-central1-a-test-cluster_created"


def test_get_cluster_info(gcp_deployer_setup):
    deployer = gcp_deployer_setup["deployer"]
    info = deployer.get_cluster_info()
    assert info['name'] == gcp_deployer_setup["cluster_name"]
    assert info['location'] == gcp_deployer_setup["location"]
    assert info['zone'] == gcp_deployer_setup["location"]
    assert info['project'] == gcp_deployer_setup["project"]
    assert 'kubeconfig_path' in info
