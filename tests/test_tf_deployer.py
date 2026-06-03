import pytest
from unittest.mock import patch, MagicMock, call
import os
import sys
import subprocess
import json
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from deployers.terraform.tf_deployer import TerraformDeployer


@pytest.fixture
def tf_deployer_setup():
    variables = {
        "project_id": "test-project",
        "cluster_name": "test-cluster",
        "location": "us-central1-a",
        "node_count": 3
    }
    # We need to mock Path.exists because TerraformDeployer.__init__ calls it
    with patch.object(Path, 'exists', return_value=True):
        deployer = TerraformDeployer(tf_dir="prebuilt/minimum", variables=variables)
    return deployer


@patch('subprocess.run')
def test_up(mock_run, tf_deployer_setup):
    tf_deployer_setup.up()

    expected_init = call(
        ["terraform", "init", "-input=false"],
        cwd=tf_deployer_setup.tf_dir,
        env=os.environ
    )
    # Wait, in my refactored tf_deployer.py, I passed `env=env` where `env = os.environ.copy()`.
    # Let's check how `mock.call` handles `env`. It will be a dict.
    # In tests, comparing dicts exactly can be tricky if env has extra stuff,
    # but since it's `os.environ.copy()`, it should match `os.environ` if we don't modify it in the test.

    expected_apply = call([
        "terraform", "apply", "-auto-approve", "-input=false",
        "-var", "project_id=test-project",
        "-var", "cluster_name=test-cluster",
        "-var", "location=us-central1-a",
        "-var", "node_count=3"
    ], cwd=tf_deployer_setup.tf_dir, env=os.environ)

    # We need to be careful about `env` in `mock_run.assert_has_calls`.
    # Let's see if we can assert calls without strict `env` matching, or provide the exact expected env.
    # Since `tf_deployer.py` uses `os.environ.copy()`, we can just check the args.

    args_list = mock_run.call_args_list
    assert len(args_list) == 2
    assert args_list[0][0][0] == ["terraform", "init", "-input=false"]
    assert args_list[0][1]['cwd'] == tf_deployer_setup.tf_dir

    assert args_list[1][0][0] == [
        "terraform", "apply", "-auto-approve", "-input=false",
        "-var", "project_id=test-project",
        "-var", "cluster_name=test-cluster",
        "-var", "location=us-central1-a",
        "-var", "node_count=3"
    ]
    assert args_list[1][1]['cwd'] == tf_deployer_setup.tf_dir


@patch('subprocess.run')
def test_down(mock_run, tf_deployer_setup):
    tf_deployer_setup.down()

    args_list = mock_run.call_args_list
    assert len(args_list) == 2
    assert args_list[0][0][0] == ["terraform", "init", "-input=false"]
    assert args_list[1][0][0] == [
        "terraform", "destroy", "-auto-approve", "-input=false",
        "-var", "project_id=test-project",
        "-var", "cluster_name=test-cluster",
        "-var", "location=us-central1-a",
        "-var", "node_count=3"
    ]


@patch('subprocess.run')
def test_get_cluster_info(mock_run, tf_deployer_setup):
    tf_output = {
        "cluster_name": {"value": "test-cluster"},
        "cluster_location": {"value": "us-central1-a"}
    }
    mock_tf_out_process = MagicMock()
    mock_tf_out_process.stdout = json.dumps(tf_output)

    mock_run.side_effect = [
        MagicMock(), # init
        mock_tf_out_process, # output
        MagicMock() # gcloud
    ]

    info = tf_deployer_setup.get_cluster_info()

    assert info["name"] == "test-cluster"
    assert info["location"] == "us-central1-a"
    assert info["project"] == "test-project"
    assert "kubeconfig_path" in info

    args_list = mock_run.call_args_list
    assert len(args_list) == 3
    assert args_list[0][0][0] == ["terraform", "init", "-input=false"]
    assert args_list[1][0][0] == ["terraform", "output", "-json"]
    # Check gcloud call with --location
    assert args_list[2][0][0] == [
        "gcloud", "container", "clusters", "get-credentials", "test-cluster",
        "--location", "us-central1-a", "--project", "test-project"
    ]


@patch('subprocess.run')
def test_get_cluster_info_regional(mock_run, tf_deployer_setup):
    tf_output = {
        "cluster_name": {"value": "test-cluster"},
        "cluster_location": {"value": "us-central1"}
    }
    mock_tf_out_process = MagicMock()
    mock_tf_out_process.stdout = json.dumps(tf_output)

    mock_run.side_effect = [
        MagicMock(), # init
        mock_tf_out_process, # output
        MagicMock() # gcloud
    ]

    info = tf_deployer_setup.get_cluster_info()

    assert info["name"] == "test-cluster"
    assert info["location"] == "us-central1"
    assert info["project"] == "test-project"

    args_list = mock_run.call_args_list
    assert len(args_list) == 3
    assert args_list[2][0][0] == [
        "gcloud", "container", "clusters", "get-credentials", "test-cluster",
        "--location", "us-central1", "--project", "test-project"
    ]


@patch('subprocess.run')
def test_get_cluster_info_local(mock_run, tf_deployer_setup):
    tf_output = {
        "cluster_name": {"value": "test-cluster"},
        "cluster_location": {"value": "local"}
    }
    mock_tf_out_process = MagicMock()
    mock_tf_out_process.stdout = json.dumps(tf_output)

    mock_run.side_effect = [
        MagicMock(), # init
        mock_tf_out_process, # output
    ]

    info = tf_deployer_setup.get_cluster_info()

    assert info["name"] == "test-cluster"
    assert info["location"] == "local"
    assert info["project"] == "test-project"
    assert "kubeconfig_path" in info

    args_list = mock_run.call_args_list
    assert len(args_list) == 2
    assert args_list[0][0][0] == ["terraform", "init", "-input=false"]
    assert args_list[1][0][0] == ["terraform", "output", "-json"]
    for call_args in args_list:
        assert "gcloud" not in call_args[0][0]


@patch('subprocess.run')
def test_get_cluster_info_local_no_project(mock_run):
    # Test that we default project to local-kind when no project is provided
    with patch.object(Path, 'exists', return_value=True):
        deployer = TerraformDeployer(tf_dir="prebuilt/minimum", variables={})

    tf_output = {
        "cluster_name": {"value": "test-cluster"},
        "cluster_location": {"value": "local"}
    }
    mock_tf_out_process = MagicMock()
    mock_tf_out_process.stdout = json.dumps(tf_output)

    mock_run.side_effect = [
        MagicMock(), # init
        mock_tf_out_process, # output
    ]

    with patch.dict(os.environ, {}, clear=True):
        info = deployer.get_cluster_info()

    assert info["name"] == "test-cluster"
    assert info["location"] == "local"
    assert info["project"] == "local-kind"
    assert "kubeconfig_path" in info



@patch.object(Path, 'exists')
def test_init_path_resolution(mock_exists):
    # Test absolute path
    abs_path = "/tmp/my-tf-stack"
    mock_exists.return_value = True
    deployer = TerraformDeployer(tf_dir=abs_path)
    assert deployer.tf_dir == abs_path

    # Test relative path in repo (terraform/<dir>)
    # We need to be careful mocking Path.exists for the fallback logic
    # In our refactored code:
    # 1. Path(tf_dir).is_absolute()
    # 2. repo_tf_path = repo_root / "terraform" / tf_path
    # 3. repo_tf_path.exists()

    with patch.object(Path, 'exists', side_effect=lambda *args, **kwargs: True):
        deployer = TerraformDeployer(tf_dir="my-repo-stack")
        assert deployer.tf_dir == str(project_root / "terraform" / "my-repo-stack")

    # Wait, my refactored code removed the "CWD" check as requested by Comment 3!
    # "Simplify supported Terraform directory paths in tf_deployer.py to just repo_root/terraform and explicitly specified directory."
    # So I should NOT test the CWD fallback.
