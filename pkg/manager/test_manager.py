import json
import unittest
from unittest.mock import MagicMock, patch
from pkg.manager.manager import ScenarioManager
from pkg.agents.verifier.base import VerificationResult

class TestScenarioManager(unittest.TestCase):

    def setUp(self):
        # Avoid side-effects during init
        with patch("pkg.manager.manager.ChaosAgent"), patch("pkg.manager.manager.VerifierAgent"):
            self.manager = ScenarioManager("my-deployment", "my-namespace")

    @patch("pkg.manager.manager.ScenarioManager._inject_chaos_with_delay")
    def test_run_chaos_and_verification_success(self, mock_inject):
        spec = {
            "name": "Test Planned load",
            "trigger": {"type": "time", "delay_seconds": 0},
            "action": {"type": "generate_load", "target": {"service_url": "http://my-service", "qps": 100}},
            "verification": {
                "pod_spec": {"type": "pod_healthy", "selector": "app=my-app"}
            }
        }

        # Mock verifier response
        mock_verification_result = VerificationResult(
            success=True,
            elapsed_time=12.5,
            reason="pod_spec succeeded",
            details={}
        )
        self.manager.verifier_agent.wait_for_condition = MagicMock(return_value=mock_verification_result)

        self.manager.run_chaos_and_verification(spec)

        mock_inject.assert_called_once_with(spec["trigger"], spec["action"])
        self.manager.verifier_agent.wait_for_condition.assert_called_once_with(spec["verification"], timeout_sec=120)

        # Check reports
        chaos_report, perf_report = self.manager.get_reports()
        self.assertEqual(chaos_report["status"], "success")
        self.assertEqual(chaos_report["verification"], mock_verification_result.model_dump())
        self.assertEqual(perf_report["deployment_time_seconds"], 12.5)
        self.assertEqual(perf_report["uptime_percentage"], 100.0)
        self.assertEqual(perf_report["resource_utilization_efficiency"], 1.0)

    @patch("pkg.manager.manager.ScenarioManager._inject_chaos_with_delay")
    def test_run_chaos_and_verification_failure(self, mock_inject):
        spec = {
            "name": "Test Planned load",
            "trigger": {"type": "time", "delay_seconds": 0},
            "action": {"type": "generate_load", "target": {"service_url": "http://my-service", "qps": 100}},
            "verification": {
                "pod_spec": {"type": "pod_healthy", "selector": "app=my-app"}
            }
        }

        # Mock verifier response to fail
        mock_verification_result = VerificationResult(
            success=False,
            elapsed_time=120.0,
            reason="pod_spec failed",
            details={}
        )
        self.manager.verifier_agent.wait_for_condition = MagicMock(return_value=mock_verification_result)

        self.manager.run_chaos_and_verification(spec)

        mock_inject.assert_called_once_with(spec["trigger"], spec["action"])
        self.manager.verifier_agent.wait_for_condition.assert_called_once_with(spec["verification"], timeout_sec=120)

        # Check reports
        chaos_report, perf_report = self.manager.get_reports()
        self.assertEqual(chaos_report["status"], "success")
        self.assertEqual(chaos_report["verification"], mock_verification_result.model_dump())
        self.assertIsNone(perf_report["deployment_time_seconds"])
        self.assertEqual(perf_report["uptime_percentage"], 0.0)
        self.assertEqual(perf_report["resource_utilization_efficiency"], 0.0)

    @patch("pkg.manager.manager.ScenarioManager._inject_chaos_with_delay")
    def test_run_chaos_and_verification_decoupled_spec(self, mock_inject):
        spec = {
            "name": "Test Planned load",
            "trigger": {"type": "time", "delay_seconds": 0},
            "action": {"type": "generate_load", "target": {"service_url": "http://my-service", "qps": 100}},
            "verification": "My Decoupled Verification"
        }
        verification_specs = [
            {
                "name": "My Decoupled Verification",
                "pod_spec": {"type": "pod_healthy", "selector": "app=my-app"}
            }
        ]

        # Mock verifier response
        mock_verification_result = VerificationResult(
            success=True,
            elapsed_time=15.0,
            reason="decoupled pod_spec succeeded",
            details={}
        )
        self.manager.verifier_agent.wait_for_condition = MagicMock(return_value=mock_verification_result)

        self.manager.run_chaos_and_verification(spec, verification_specs)

        mock_inject.assert_called_once_with(spec["trigger"], spec["action"])
        self.manager.verifier_agent.wait_for_condition.assert_called_once_with(verification_specs[0], timeout_sec=120)

        # Check reports
        chaos_report, perf_report = self.manager.get_reports()
        self.assertEqual(chaos_report["status"], "success")
        self.assertEqual(chaos_report["verification"], mock_verification_result.model_dump())
        self.assertEqual(perf_report["deployment_time_seconds"], 15.0)
        self.assertEqual(perf_report["uptime_percentage"], 100.0)
        self.assertEqual(perf_report["resource_utilization_efficiency"], 1.0)

if __name__ == "__main__":
    unittest.main()
