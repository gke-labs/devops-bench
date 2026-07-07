import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from pkg.agents.verifier.verifier import VerifierAgent
from pkg.agents.verifier.pod_healthy import PodHealthyVerifier
from pkg.agents.verifier.scaling_complete import ScalingCompleteVerifier

class TestVerifierAgent(unittest.TestCase):

    def setUp(self):
        self.verifier = VerifierAgent()

    @patch("subprocess.run")
    def test_pod_healthy_verifier_check_status_success(self, mock_run):
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

        p_verifier = PodHealthyVerifier(selector="app=my-app")
        details = p_verifier._get_pods_details()
        success = p_verifier._check_pods_status(details)

        self.assertTrue(success)
        self.assertEqual(len(details["items"]), 2)

    @patch("subprocess.run")
    def test_pod_healthy_verifier_check_status_failure(self, mock_run):
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

        p_verifier = PodHealthyVerifier(selector="app=my-app")
        details = p_verifier._get_pods_details()
        success = p_verifier._check_pods_status(details)

        self.assertFalse(success)

    @patch("subprocess.run")
    def test_scaling_complete_verifier_check_scaling_success(self, mock_run):
        mock_output = json.dumps({"status": {"readyReplicas": 3}})
        mock_run.return_value = MagicMock(
            stdout=mock_output, returncode=0
        )

        s_verifier = ScalingCompleteVerifier(deployment="my-dep", min_replicas=3)
        success, details = s_verifier._check_scaling()

        self.assertTrue(success)
        self.assertIn("Ready replicas (3) >= min replicas (3)", details["reason"])

    @patch("subprocess.run")
    def test_pod_healthy_verifier_verify_wait_success(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="pod/my-pod condition met", returncode=0
        )

        p_verifier = PodHealthyVerifier(selector="app=my-app")
        result = p_verifier.verify(timeout_sec=60)

        self.assertTrue(result.success)
        self.assertEqual(result.reason, "Condition met via kubectl wait")

    @patch("subprocess.run")
    def test_pod_healthy_verifier_verify_wait_failure_fallback_success(self, mock_run):
        # Mock wait fails, but get pods status succeeds (running fallback)
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "kubectl wait", stderr="timed out"),
            MagicMock(
                stdout=json.dumps({"items": [{"status": {"phase": "Running"}}]}),
                returncode=0
            )
        ]

        p_verifier = PodHealthyVerifier(selector="app=my-app")
        result = p_verifier.verify(timeout_sec=60)

        self.assertTrue(result.success)
        self.assertEqual(result.reason, "Condition met via polling fallback")

    @patch("pkg.agents.verifier.scaling_complete.ScalingCompleteVerifier._check_scaling")
    @patch("time.sleep")
    def test_scaling_complete_verifier_verify_polling_success(self, mock_sleep, mock_check):
        mock_check.side_effect = [
            (False, {"reason": "not yet"}),
            (True, {"reason": "done"}),
        ]

        s_verifier = ScalingCompleteVerifier(deployment="my-dep", min_replicas=2)
        result = s_verifier.verify(timeout_sec=60)

        self.assertTrue(result.success)
        self.assertEqual(result.reason, "Scaling complete: done")
        self.assertEqual(mock_sleep.call_count, 1)

    @patch("subprocess.run")
    def test_wait_for_condition_compound_success(self, mock_run):
        def run_side_effect(cmd, *args, **kwargs):
            if "wait" in cmd:
                return MagicMock(stdout="pod/my-pod condition met", returncode=0)
            elif "deployment" in cmd:
                return MagicMock(stdout=json.dumps({"status": {"readyReplicas": 2}}), returncode=0)
            return MagicMock(stdout="", returncode=0)
            
        mock_run.side_effect = run_side_effect

        spec = {
            "pod_spec": {"type": "pod_healthy", "selector": "app=my-app"},
            "scaling_spec": {"type": "scaling_complete", "deployment": "my-dep", "min_replicas": 2}
        }
        result = self.verifier.wait_for_condition(spec, timeout_sec=60)

        self.assertTrue(result.success)
        self.assertIn("pod_spec succeeded", result.reason)
        self.assertIn("scaling_spec succeeded", result.reason)

    @patch("subprocess.run")
    def test_wait_for_condition_compound_failure(self, mock_run):
        def run_side_effect(cmd, *args, **kwargs):
            if "wait" in cmd:
                raise subprocess.CalledProcessError(1, "kubectl wait", stderr="timed out")
            elif "deployment" in cmd:
                return MagicMock(stdout=json.dumps({"status": {"readyReplicas": 2}}), returncode=0)
            elif "pods" in cmd:
                return MagicMock(stdout=json.dumps({"items": []}), returncode=0)
            return MagicMock(stdout="", returncode=0)

        mock_run.side_effect = run_side_effect

        spec = {
            "pod_spec": {"type": "pod_healthy", "selector": "app=my-app"},
            "scaling_spec": {"type": "scaling_complete", "deployment": "my-dep", "min_replicas": 2}
        }
        result = self.verifier.wait_for_condition(spec, timeout_sec=60)

        self.assertFalse(result.success)
        self.assertIn("pod_spec failed", result.reason)
        self.assertIn("scaling_spec succeeded", result.reason)

if __name__ == "__main__":
    unittest.main()
