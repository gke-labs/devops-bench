import json
import threading
import time
import subprocess
import datetime
from pkg.agents.chaos.chaos import ChaosAgent

def log(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {msg}", flush=True)

class ScenarioManager:
    def __init__(self, target_deployment, namespace):
        self.target_deployment = target_deployment
        self.namespace = namespace
        self.chaos_active_event = threading.Event()
        self.chaos_agent = ChaosAgent()
        self.chaos_agent.chaos_active_event = self.chaos_active_event
        self.result_holder = {"chaos_report": {}, "perf_report": {}}
        self.baseline_generation = 0

    def _inject_chaos_with_delay(self, trigger, action):
        delay = trigger.get("delay_seconds", 0)
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
        time.sleep(3) # Give it 3 seconds to establish the tunnel
        
        # 2. Redirect Chaos Agent load generation to localhost!
        local_action = action.copy()
        local_action["target"] = local_action.get("target", {}).copy()
        local_action["target"]["service_url"] = "http://localhost:8080"
        
        log(f"[ScenarioManager] Triggering chaos action: generate_load on http://localhost:8080")
        try:
            self.chaos_agent.inject_fault(local_action)
        except Exception as e:
            log(f"[ScenarioManager] Error during chaos injection: {e}")
        
        # 3. Terminate port-forwarding after load generation is complete
        log("[ScenarioManager] Terminating GKE port-forward...")
        if hasattr(self, "pf_process"):
            self.pf_process.terminate()
            self.pf_process.wait()
            log("[ScenarioManager] Port-forward terminated.")