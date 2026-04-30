import unittest
from unittest.mock import patch
import os
import sys

# Add project root to path to resolve imports correctly
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from deployers.gcp.gcp_deployer import GCPDeployer

class TestGCPDeployer(unittest.TestCase):
    def setUp(self):
        self.project = "test-project"
        self.zone = "test-zone"
        self.cluster_name = "test-cluster"
        self.deployer = GCPDeployer(self.project, self.zone, self.cluster_name)

    @patch('subprocess.run')
    def test_up(self, mock_run):
        self.deployer.up()
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        self.assertIn("kubetest2", cmd)
        self.assertIn("gke", cmd)
        self.assertIn("--up", cmd)
        self.assertIn(self.project, cmd)
        
        # Verify env has bin_dir in PATH
        env = kwargs.get('env')
        self.assertIsNotNone(env)
        self.assertIn(self.deployer.bin_dir, env['PATH'])
        
    @patch('subprocess.run')
    def test_up_with_config(self, mock_run):
        deployer = GCPDeployer(self.project, self.zone, self.cluster_name, machine_type="n1-standard-4", num_nodes=5)
        deployer.up()
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        self.assertIn("--machine-type", cmd)
        self.assertIn("n1-standard-4", cmd)
        self.assertIn("--num-nodes", cmd)
        self.assertIn("5", cmd)

    @patch('subprocess.run')
    def test_down(self, mock_run):
        self.deployer.down()
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        self.assertIn("kubetest2", cmd)
        self.assertIn("gke", cmd)
        self.assertIn("--down", cmd)
        self.assertIn(self.project, cmd)
        
        env = kwargs.get('env')
        self.assertIsNotNone(env)
        self.assertIn(self.deployer.bin_dir, env['PATH'])

    def test_get_cluster_info(self):
        info = self.deployer.get_cluster_info()
        self.assertEqual(info['name'], self.cluster_name)
        self.assertEqual(info['zone'], self.zone)
        self.assertEqual(info['project'], self.project)
        self.assertTrue('kubeconfig_path' in info)

if __name__ == '__main__':
    unittest.main()
