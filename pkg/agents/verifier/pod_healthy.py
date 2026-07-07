import subprocess
import time
import json
from typing import Literal, Optional
from pkg.agents.verifier.base import BaseVerifier, VerificationResult

class PodHealthyVerifier(BaseVerifier):
    type: Literal["pod_healthy"] = "pod_healthy"
    selector: str
    namespace: Optional[str] = None

    def verify(self, timeout_sec: int) -> VerificationResult:
        start_time = time.time()
        # Try using kubectl wait
        cmd = [
            "kubectl",
            "wait",
            "--for=condition=Ready",
            "pod",
            "-l",
            self.selector,
            f"--timeout={timeout_sec}s",
        ]
        if self.namespace:
            cmd.extend(["-n", self.namespace])

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            )
            return VerificationResult(
                success=True,
                elapsed_time=time.time() - start_time,
                reason="Condition met via kubectl wait",
                details={"output": result.stdout.strip()},
            )
        except subprocess.CalledProcessError as e:
            # Fallback or get details on failure
            elapsed = time.time() - start_time
            details = self._get_pods_details()
            success = self._check_pods_status(details)
            if success:
                return VerificationResult(
                    success=True,
                    elapsed_time=elapsed,
                    reason="Condition met via polling fallback",
                    details=details,
                )
            
            return VerificationResult(
                success=False,
                elapsed_time=elapsed,
                reason=f"kubectl wait failed or timed out: {e.stderr.strip()}",
                details=details,
            )

    def _get_pods_details(self) -> dict:
        try:
            cmd = ["kubectl", "get", "pods", "-l", self.selector, "-o", "json"]
            if self.namespace:
                cmd.extend(["-n", self.namespace])
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            )
            return json.loads(result.stdout)
        except Exception as e:
            return {"error": str(e)}

    def _check_pods_status(self, details: dict) -> bool:
        items = details.get("items", [])
        return len(items) > 0 and all(
            p.get("status", {}).get("phase") == "Running" for p in items
        )
