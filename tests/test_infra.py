import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.infra import main

class TestInfraCLI(unittest.TestCase):

    @patch('deployers.gcp.gcp_deployer.GCPDeployer.up')
    def test_gcp_up(self, mock_up):
        test_args = ["infra.py", "gcp", "up", "--project", "my-project", "--cluster-name", "my-cluster"]
        with patch.object(sys, 'argv', test_args):
            main()
        mock_up.assert_called_once()

    @patch('deployers.gcp.gcp_deployer.GCPDeployer.down')
    def test_gcp_down(self, mock_down):
        test_args = ["infra.py", "gcp", "down", "--project", "my-project", "--cluster-name", "my-cluster"]
        with patch.object(sys, 'argv', test_args):
            main()
        mock_down.assert_called_once()

if __name__ == '__main__':
    unittest.main()
