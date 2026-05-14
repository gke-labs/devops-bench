import unittest
from unittest.mock import patch, MagicMock
import os

from pkg.agents.chaos.chaos import ChaosAgent

class TestChaosAgent(unittest.TestCase):

    @patch('subprocess.run')
    def test_inject_fault_generate_load(self, mock_run):
        # Setup
        mock_run.return_value = MagicMock(stdout="mock stdout", stderr="mock stderr", returncode=0)
        agent = ChaosAgent()
        action_spec = {
            "type": "generate_load",
            "target": {
                "service_url": "http://localhost:8082",
                "qps": 100,
                "duration": "10s",
                "concurrency": 2
            }
        }

        # Execute
        agent.inject_fault(action_spec)

        # Verify
        fortio_path = os.path.expanduser("~/go/bin/fortio")
        expected_cmd = [
            fortio_path, "load",
            "-qps", "100",
            "-t", "10s",
            "-c", "2",
            "http://localhost:8082"
        ]
        mock_run.assert_called_once_with(
            expected_cmd,
            capture_output=True,
            check=True,
            text=True
        )

if __name__ == '__main__':
    unittest.main()
