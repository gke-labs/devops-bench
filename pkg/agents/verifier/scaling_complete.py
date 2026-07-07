import subprocess
import time
import json
from typing import Literal, Optional
from pkg.agents.verifier.base import BaseVerifier, VerificationResult

class ScalingCompleteVerifier(BaseVerifier):
    type: Literal["scaling_complete"] = "scaling_complete"
    deployment: str
    min_replicas: int = 1
    namespace: Optional[str] = None

    def verify(self, timeout_sec: int) -> VerificationResult:
        start_time = time.time()
        delay = 1
        max_delay = 10

        while time.time() - start_time < timeout_sec:
            success, details = self._check_scaling()
            if success:
                return VerificationResult(
                    success=True,
                    elapsed_time=time.time() - start_time,
                    reason=f"Scaling complete: {details.get('reason')}",
                    details=details,
                )
            time.sleep(delay)
            delay = min(delay * 2, max_delay)

        # Last check on timeout
        success, details = self._check_scaling()
        return VerificationResult(
            success=success,
            elapsed_time=time.time() - start_time,
            reason=f"Timeout reached: {details.get('reason')}",
            details=details,
        )

    def _check_scaling(self) -> (bool, dict):
        try:
            cmd = [
                "kubectl",
                "get",
                "deployment",
                self.deployment,
                "-o",
                "json",
            ]
            if self.namespace:
                cmd.extend(["-n", self.namespace])

            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            )
            dep_data = json.loads(result.stdout)
            ready_replicas = dep_data.get("status", {}).get("readyReplicas", 0)
            success = ready_replicas >= self.min_replicas
            reason = (
                f"Ready replicas ({ready_replicas}) >= min replicas ({self.min_replicas})"
                if success
                else f"Ready replicas ({ready_replicas}) < min replicas ({self.min_replicas})"
            )
            return success, {"reason": reason, "deployment": dep_data}
        except subprocess.CalledProcessError as e:
            return False, {
                "reason": f"Failed to get deployment: {e.stderr.strip()}"
            }
        except json.JSONDecodeError:
            return False, {"reason": "Failed to parse deployment JSON"}
