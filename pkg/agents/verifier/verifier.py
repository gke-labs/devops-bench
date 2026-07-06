import time

from pkg.agents.verifier.base import VerificationResult
from pkg.agents.verifier.spec import VerificationSpec


class VerifierAgent:
    """Uses kubectl to validate cluster state."""

    def wait_for_condition(
        self, spec: VerificationSpec | dict | list, timeout_sec: int = 120
    ) -> VerificationResult:
        """Waits for condition using watch or polling.
        Supports compound specifications (list or dict of specs) as well as single specs.
        """
        if not isinstance(spec, VerificationSpec):
            spec = VerificationSpec(spec)

        root = spec.root
        start_time = time.time()

        if isinstance(root, list):
            results = []
            overall_success = True
            overall_reason = []
            for i, sub_spec in enumerate(root):
                elapsed = time.time() - start_time
                remaining_timeout = max(1, timeout_sec - int(elapsed))
                sub_result = self.wait_for_condition(
                    VerificationSpec(sub_spec), timeout_sec=remaining_timeout
                )
                results.append(sub_result)
                if not sub_result.success:
                    overall_success = False
                    overall_reason.append(f"spec[{i}] failed: {sub_result.reason}")
                else:
                    overall_reason.append(f"spec[{i}] succeeded")
            return VerificationResult(
                success=overall_success,
                elapsed_time=time.time() - start_time,
                reason="; ".join(overall_reason),
                details=results,
            )

        if isinstance(root, dict):
            results = {}
            overall_success = True
            overall_reason = []
            for name, sub_spec in root.items():
                elapsed = time.time() - start_time
                remaining_timeout = max(1, timeout_sec - int(elapsed))
                sub_result = self.wait_for_condition(
                    VerificationSpec(sub_spec), timeout_sec=remaining_timeout
                )
                results[name] = sub_result
                if not sub_result.success:
                    overall_success = False
                    overall_reason.append(f"{name} failed: {sub_result.reason}")
                else:
                    overall_reason.append(f"{name} succeeded")
            return VerificationResult(
                success=overall_success,
                elapsed_time=time.time() - start_time,
                reason="; ".join(overall_reason),
                details=results,
            )

        # root is a SingleVerificationSpec (PodHealthyVerifier or ScalingCompleteVerifier)
        return root.verify(timeout_sec)
