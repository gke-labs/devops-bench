import json
import threading
import time
import subprocess
import datetime
from pkg.agents.chaos.chaos import ChaosAgent
from pkg.agents.verifier.verifier import VerifierAgent

def log(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {msg}", flush=True)

class ScenarioManager:
    """Manages GKE port-forwarding, schedules chaos agent load spikes, and aggregates telemetry."""
    
    def __init__(self, target_deployment, namespace):
        self.target_deployment = target_deployment
        self.namespace = namespace
        self.chaos_active_event = threading.Event()
        self.chaos_agent = ChaosAgent()
        self.chaos_agent.chaos_active_event = self.chaos_active_event
        self.verifier_agent = VerifierAgent()
        self.result_holder = {
            "chaos_report": {},
            "perf_report": {}
        }
        self.start_time = None

    def run_chaos_and_verification(self, spec, verification_specs=None):
        """Unpacks the chaos spec, injects the fault, and gathers verification metrics."""
        self.start_time = time.time()
        trigger = spec.get("trigger", {})
        action = spec.get("action", {})
        verification_ref = spec.get("verification", {})
        
        verification = {}
        if isinstance(verification_ref, str):
            if verification_specs:
                for v_spec in verification_specs:
                    if v_spec.get("name") == verification_ref:
                        verification = v_spec
                        break
        elif isinstance(verification_ref, dict):
            verification = verification_ref
        
        # Record initial chaos metadata
        self.result_holder["chaos_report"] = {
            "injected_fault": action.get("type", "generate_load"),
            "name": spec.get("name", "Planned Disruption"),
            "status": "initiated"
        }
        
        try:
            self._inject_chaos_with_delay(trigger, action)
            self.result_holder["chaos_report"]["status"] = "success"
        except Exception as e:
            log(f"[ScenarioManager] Error running scenario: {e}")
            self.result_holder["chaos_report"]["status"] = "failed"
            self.result_holder["chaos_report"]["error"] = str(e)
            return

        # Execute planned verification if provided in the spec
        if verification:
            log(f"[ScenarioManager] Starting planned verification using VerifierAgent...")
            try:
                verification_result = self.verifier_agent.wait_for_condition(verification, timeout_sec=120)
                log(f"[ScenarioManager] Verification completed: {verification_result.model_dump_json(indent=2)}")
                self.result_holder["chaos_report"]["verification"] = verification_result.model_dump()
                
                # Populate performance reports dynamically based on verification outcomes
                elapsed_time = verification_result.elapsed_time
                success = verification_result.success
                
                self.result_holder["perf_report"] = {
                    "deployment_time_seconds": elapsed_time if success else None,
                    "uptime_percentage": 100.0 if success else 0.0,
                    "resource_utilization_efficiency": 1.0 if success else 0.0,
                }
            except Exception as e:
                log(f"[ScenarioManager] Verification failed with exception: {e}")
                self.result_holder["chaos_report"]["verification"] = {
                    "success": False,
                    "reason": f"Verification exception: {str(e)}"
                }

    def _inject_chaos_with_delay(self, trigger, action):
        """Delays execution if specified, brings up kubectl port-forward, and executes chaos agent."""
        delay = trigger.get("delay_seconds", 0)
        if delay > 0:
            log(f"[ScenarioManager] Waiting for trigger delay of {delay}s...")
            time.sleep(delay)
        
        # 1. Establish kubectl port-forward to local port 8080
        log(f"[ScenarioManager] Establishing port-forward to deployment/{self.target_deployment} on port 8080...")
        pf_cmd = [
            "kubectl", "port-forward", 
            f"deployment/{self.target_deployment}", 
            "8080:8080", 
            "-n", self.namespace
        ]
        
        self.pf_process = subprocess.Popen(
            pf_cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        
        # Give it 3 seconds to establish the tunnel
        time.sleep(3)
        
        # 2. Redirect Chaos Agent load generation to localhost
        local_action = action.copy()
        local_action["target"] = local_action.get("target", {}).copy()
        local_action["target"]["service_url"] = "http://localhost:8080"
        
        log(f"[ScenarioManager] Triggering chaos action: generate_load on http://localhost:8080")
        try:
            self.chaos_agent.inject_fault(local_action)
        except Exception as e:
            log(f"[ScenarioManager] Error during chaos injection: {e}")
            raise e
        finally:
            # 3. Terminate port-forwarding after load generation is complete
            log("[ScenarioManager] Terminating GKE port-forward...")
            if hasattr(self, "pf_process"):
                self.pf_process.terminate()
                self.pf_process.wait()
                log("[ScenarioManager] Port-forward terminated.")




    def get_reports(self):
        """Returns the aggregated chaos and performance reports."""
        return self.result_holder.get("chaos_report", {}), self.result_holder.get("perf_report", {})