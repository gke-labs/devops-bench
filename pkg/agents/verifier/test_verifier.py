import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from pkg.agents.verifier.verifier import VerifierAgent


class TestVerifierAgent(unittest.TestCase):

    def setUp(self):
        self.verifier = VerifierAgent()

    @patch("subprocess.run")
    def test_check_condition_pod_healthy_success(self, mock_run):
        mock_output = json.dumps(
            {
                "items": [
                    {"status": {"phase": "Running"}},
                    {"status": {"phase": "Running"}},
                ]
            }
        )
        mock_run.return_value = MagicMock(
            stdout=mock_output, returncode=0
        )

        spec = {"type": "pod_healthy", "selector": "app=my-app"}
        success, details = self.verifier._check_condition(spec)

        self.assertTrue(success)
        self.assertEqual(details["reason"], "All pods running")
        self.assertEqual(len(details["items"]), 2)

    @patch("subprocess.run")
    def test_check_condition_pod_healthy_failure_not_running(
        self, mock_run
    ):
        mock_output = json.dumps(
            {
                "items": [
                    {"status": {"phase": "Running"}},
                    {"status": {"phase": "Pending"}},
                ]
            }
        )
        mock_run.return_value = MagicMock(
            stdout=mock_output, returncode=0
        )

        spec = {"type": "pod_healthy", "selector": "app=my-app"}
        success, details = self.verifier._check_condition(spec)

        self.assertFalse(success)
        self.assertEqual(
            details["reason"], "Some pods not running or no pods found"
        )

    @patch("subprocess.run")
    def test_check_condition_scaling_complete_success(self, mock_run):
        mock_output = json.dumps({"status": {"readyReplicas": 3}})
        mock_run.return_value = MagicMock(
            stdout=mock_output, returncode=0
        )

        spec = {
            "type": "scaling_complete",
            "deployment": "my-dep",
            "min_replicas": 3,
        }
        success, details = self.verifier._check_condition(spec)

        self.assertTrue(success)
        self.assertIn("Ready replicas (3) >= min replicas (3)", details["reason"])

    @patch("subprocess.run")
    def test_wait_for_condition_pod_healthy_wait_success(self, mock_run):
        # Mock kubectl wait success
        mock_run.return_value = MagicMock(
            stdout="pod/my-pod condition met", returncode=0
        )

        spec = {"type": "pod_healthy", "selector": "app=my-app"}
        result = self.verifier.wait_for_condition(spec, timeout=60)

        self.assertTrue(result["success"])
        self.assertEqual(result["reason"], "Condition met via kubectl wait")
        self.assertIn("kubectl", mock_run.call_args[0][0])
        self.assertIn("wait", mock_run.call_args[0][0])

    @patch("subprocess.run")
    def test_wait_for_condition_pod_healthy_wait_failure_fallback(
        self, mock_run
    ):
        # Mock kubectl wait failure (timeout or error)
        mock_run.side_effect = [
            subprocess.CalledProcessError(
                1, "kubectl wait", stderr="timed out"
            ),  # wait fails
            MagicMock(
                stdout=json.dumps(
                    {"items": [{"status": {"phase": "Running"}}]}
                ),
                returncode=0,
            ),  # get pods for details
        ]

        spec = {"type": "pod_healthy", "selector": "app=my-app"}
        result = self.verifier.wait_for_condition(spec, timeout=60)

        self.assertFalse(result["success"])
        self.assertIn("kubectl wait failed or timed out", result["reason"])
        self.assertIn("items", result["details"])

    @patch("pkg.agents.verifier.verifier.VerifierAgent._check_condition")
    @patch("time.sleep")
    def test_wait_polling_backoff_success(self, mock_sleep, mock_check):
        # Mock _check_condition to fail first, then succeed
        mock_check.side_effect = [
            (False, {"reason": "not yet"}),
            (True, {"reason": "done"}),
        ]

        spec = {"type": "scaling_complete", "deployment": "my-dep"}
        result = self.verifier._wait_polling_backoff(spec, timeout=60)

        self.assertTrue(result["success"])
        self.assertEqual(result["reason"], "Condition met via polling")
        self.assertEqual(mock_sleep.call_count, 1)
        mock_sleep.assert_called_with(1)  # Initial delay


if __name__ == "__main__":
    unittest.main()
