import sys
from pathlib import Path
from unittest.mock import patch

# Ensure project root is in path
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.infra import main  # noqa: E402


@patch("deployers.gcp.gcp_deployer.GCPDeployer.up")
def test_gcp_up(mock_up):
    test_args = ["infra.py", "gcp", "up", "--project", "my-project", "--cluster-name", "my-cluster"]
    with patch.object(sys, "argv", test_args):
        main()
    mock_up.assert_called_once()


@patch("deployers.gcp.gcp_deployer.GCPDeployer.down")
def test_gcp_down(mock_down):
    test_args = [
        "infra.py",
        "gcp",
        "down",
        "--project",
        "my-project",
        "--cluster-name",
        "my-cluster",
    ]
    with patch.object(sys, "argv", test_args):
        main()
    mock_down.assert_called_once()


@patch("deployers.tf.tf_deployer.TFDeployer.up")
def test_gcp_tofu_up(mock_up):
    test_args = [
        "infra.py",
        "--use-tofu",
        "gcp",
        "up",
        "--project",
        "my-project",
        "--cluster-name",
        "my-cluster",
    ]
    with patch.object(sys, "argv", test_args):
        main()
    mock_up.assert_called_once()


@patch("deployers.tf.tf_deployer.TFDeployer.down")
def test_gcp_tofu_down(mock_down):
    test_args = [
        "infra.py",
        "--use-tofu",
        "gcp",
        "down",
        "--project",
        "my-project",
        "--cluster-name",
        "my-cluster",
    ]
    with patch.object(sys, "argv", test_args):
        main()
    mock_down.assert_called_once()


@patch("deployers.tf.tf_deployer.TFDeployer.up")
def test_kind_up(mock_up):
    test_args = ["infra.py", "kind", "up", "--cluster-name", "my-local-cluster"]
    with patch.object(sys, "argv", test_args):
        main()
    mock_up.assert_called_once()


@patch("deployers.tf.tf_deployer.TFDeployer.up")
def test_kind_tofu_up(mock_up):
    test_args = ["infra.py", "--use-tofu", "kind", "up", "--cluster-name", "my-local-cluster"]
    with patch.object(sys, "argv", test_args):
        main()
    mock_up.assert_called_once()
