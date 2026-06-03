import pytest
from unittest.mock import patch, MagicMock
import sys
import os
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.infra import main


@patch('deployers.gcp.gcp_deployer.GCPDeployer.up')
def test_gcp_up(mock_up):
    test_args = [
        "infra.py", "gcp", "up", "--project", "my-project", "--cluster-name",
        "my-cluster"
    ]
    with patch.object(sys, 'argv', test_args):
        main()
    mock_up.assert_called_once()


@patch('deployers.gcp.gcp_deployer.GCPDeployer.down')
def test_gcp_down(mock_down):
    test_args = [
        "infra.py", "gcp", "down", "--project", "my-project", "--cluster-name",
        "my-cluster"
    ]
    with patch.object(sys, 'argv', test_args):
        main()
    mock_down.assert_called_once()


@patch('deployers.terraform.tf_deployer.TerraformDeployer.up')
def test_gcp_terraform_up(mock_up):
    test_args = [
        "infra.py", "--use-terraform", "gcp", "up", "--project", "my-project",
        "--cluster-name", "my-cluster"
    ]
    with patch.object(sys, 'argv', test_args):
        main()
    mock_up.assert_called_once()


@patch('deployers.terraform.tf_deployer.TerraformDeployer.down')
def test_gcp_terraform_down(mock_down):
    test_args = [
        "infra.py", "--use-terraform", "gcp", "down", "--project", "my-project",
        "--cluster-name", "my-cluster"
    ]
    with patch.object(sys, 'argv', test_args):
        main()
    mock_down.assert_called_once()


@patch('deployers.terraform.tf_deployer.TerraformDeployer.up')
def test_kind_up(mock_up):
    test_args = [
        "infra.py", "kind", "up", "--cluster-name", "my-local-cluster"
    ]
    with patch.object(sys, 'argv', test_args):
        main()
    mock_up.assert_called_once()


@patch('deployers.terraform.tf_deployer.TerraformDeployer.up')
def test_kind_terraform_up(mock_up):
    test_args = [
        "infra.py", "--use-terraform", "kind", "up", "--cluster-name", "my-local-cluster"
    ]
    with patch.object(sys, 'argv', test_args):
        main()
    mock_up.assert_called_once()

