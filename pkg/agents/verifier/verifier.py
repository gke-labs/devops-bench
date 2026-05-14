import json
import subprocess
import time


class VerifierAgent:
    """Uses kubectl to validate cluster state."""

    def wait_for_condition(
        self, spec: dict, timeout: int = 120
    ) -> dict:
        """Waits for condition using watch (kubectl wait) or polling with backoff."""
        c_type = spec.get("type")
        start_time = time.time()

        if c_type == "pod_healthy":
            # Try using kubectl wait (Option 3)
            selector = spec.get("selector")
            namespace = spec.get("namespace")
            if selector:
                cmd = [
                    "kubectl",
                    "wait",
                    "--for=condition=Ready",
                    "pod",
                    "-l",
                    selector,
                    f"--timeout={timeout}s",
                ]
                if namespace:
                    cmd.extend(["-n", namespace])

                try:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, check=True
                    )
                    return {
                        "success": True,
                        "elapsed_time": time.time() - start_time,
                        "reason": "Condition met via kubectl wait",
                        "details": {"output": result.stdout.strip()},
                    }
                except subprocess.CalledProcessError as e:
                    # Fallback or get details on failure
                    elapsed = time.time() - start_time
                    # Get details for failure report (Option 2)
                    details = self._get_pods_details(selector, namespace)
                    return {
                        "success": False,
                        "elapsed_time": elapsed,
                        "reason": f"kubectl wait failed or timed out: {e.stderr.strip()}",
                        "details": details,
                    }

        # Fallback to Polling with Exponential Backoff (Option 1)
        return self._wait_polling_backoff(spec, timeout)

    def _wait_polling_backoff(self, spec: dict, timeout: int) -> dict:
        start_time = time.time()
        delay = 1  # Start with 1s delay (Option 1)
        max_delay = 10

        while time.time() - start_time < timeout:
            success, details = self._check_condition(spec)
            if success:
                return {
                    "success": True,
                    "elapsed_time": time.time() - start_time,
                    "reason": "Condition met via polling",
                    "details": details,
                }

            time.sleep(delay)
            delay = min(delay * 2, max_delay)  # Exponential backoff

        # Timeout
        success, details = self._check_condition(spec)
        return {
            "success": success,
            "elapsed_time": time.time() - start_time,
            "reason": "Timeout reached during polling",
            "details": details,
        }

    def _check_condition(self, spec: dict) -> (bool, dict):
        """Checks condition and returns (success, details)."""
        c_type = spec.get("type")

        if c_type == "pod_healthy":
            selector = spec.get("selector")
            namespace = spec.get("namespace")
            details = self._get_pods_details(selector, namespace)
            items = details.get("items", [])
            success = len(items) > 0 and all(
                p.get("status", {}).get("phase") == "Running" for p in items
            )
            reason = (
                "All pods running"
                if success
                else "Some pods not running or no pods found"
            )
            return success, {"reason": reason, "items": items}

        elif c_type == "scaling_complete":
            deployment_name = spec.get("deployment")
            min_replicas = spec.get("min_replicas", 1)
            namespace = spec.get("namespace")
            if not deployment_name:
                return False, {"reason": "Deployment name missing"}

            try:
                cmd = [
                    "kubectl",
                    "get",
                    "deployment",
                    deployment_name,
                    "-o",
                    "json",
                ]
                if namespace:
                    cmd.extend(["-n", namespace])

                result = subprocess.run(
                    cmd, capture_output=True, text=True, check=True
                )
                dep_data = json.loads(result.stdout)
                ready_replicas = (
                    dep_data.get("status", {}).get("readyReplicas", 0)
                )
                success = ready_replicas >= min_replicas
                reason = (
                    f"Ready replicas ({ready_replicas}) >= min replicas ({min_replicas})"
                    if success
                    else f"Ready replicas ({ready_replicas}) < min replicas ({min_replicas})"
                )
                return success, {"reason": reason, "deployment": dep_data}
            except subprocess.CalledProcessError as e:
                return False, {
                    "reason": f"Failed to get deployment: {e.stderr.strip()}"
                }
            except json.JSONDecodeError:
                return False, {"reason": "Failed to parse deployment JSON"}

        return False, {"reason": f"Unknown condition type: {c_type}"}

    def _get_pods_details(self, selector: str, namespace: str) -> dict:
        """Helper to get pods details."""
        if not selector:
            return {}
        try:
            cmd = ["kubectl", "get", "pods", "-l", selector, "-o", "json"]
            if namespace:
                cmd.extend(["-n", namespace])

            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            )
            return json.loads(result.stdout)
        except Exception as e:
            return {"error": str(e)}
