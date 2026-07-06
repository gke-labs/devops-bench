import atexit
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from deepeval.tracing import observe

# Global reference to keep track of the port-forward process
_PF_PROCESS = None
_STDOUT_LOG = None
_STDERR_LOG = None


def _ensure_port_forward(local_port: int):
    """Lazily establishes a background kubectl port-forward if the local port is closed."""
    global _PF_PROCESS, _STDOUT_LOG, _STDERR_LOG
    # Check if the port is already open (established externally or already running)
    port_in_use = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(("127.0.0.1", local_port))
            port_in_use = True
    except (TimeoutError, ConnectionRefusedError):
        pass

    if port_in_use:
        # Port is already open, nothing to do!
        return
    # Port is closed, establish the port-forward
    service_name = os.environ.get("AGENT_SERVICE_NAME", "hermes-agent")
    namespace = os.environ.get("AGENT_NAMESPACE", "default")
    remote_port = os.environ.get("AGENT_PORT", str(local_port))
    agent_context = os.environ.get("AGENT_CLUSTER_CONTEXT")
    print(
        f"[HTTP Runner] Port {local_port} is closed. Establishing port-forward to svc/{service_name}..."
    )
    pf_cmd = [
        "kubectl",
        "port-forward",
        f"svc/{service_name}",
        f"{local_port}:{remote_port}",
        "-n",
        namespace,
    ]
    if agent_context:
        pf_cmd.extend(["--context", agent_context])

    stdout_log_path = "agent_port_forward_stdout.log"
    stderr_log_path = "agent_port_forward_stderr.log"
    _STDOUT_LOG = open(stdout_log_path, "w")  # noqa: SIM115
    _STDERR_LOG = open(stderr_log_path, "w")  # noqa: SIM115

    _PF_PROCESS = subprocess.Popen(pf_cmd, stdout=_STDOUT_LOG, stderr=_STDERR_LOG)
    time.sleep(3)  # Wait for it to establish

    if _PF_PROCESS.poll() is not None:
        _STDOUT_LOG.close()
        _STDERR_LOG.close()
        with open(stderr_log_path) as f:
            stderr_content = f.read()
        print(f"[HTTP Runner] Error: Port-forward failed to start. Stderr:\n{stderr_content}")
        sys.exit(1)
    else:
        print(f"[HTTP Runner] Port-forward established successfully on port {local_port}.")

        # Register cleanup handler exactly once when we spawn the process
        def cleanup_pf():
            global _PF_PROCESS, _STDOUT_LOG, _STDERR_LOG
            if _PF_PROCESS is not None:
                print("[HTTP Runner] Terminating agent port-forward...")
                _PF_PROCESS.terminate()
                _PF_PROCESS.wait()
                _PF_PROCESS = None
            if _STDOUT_LOG is not None:
                _STDOUT_LOG.close()
            if _STDERR_LOG is not None:
                _STDERR_LOG.close()
            print("[HTTP Runner] Agent port-forward terminated.")

        atexit.register(cleanup_pf)


@observe()
def run_kubeagents(prompt, _context=None):
    """Runs the agent by sending an HTTP request."""

    local_port = int(os.environ.get("AGENT_LOCAL_PORT", "8642"))
    api_path = os.environ.get(
        "AGENT_API_PATH", "/v1/responses"
    )  # Adjust path to match your agent gateway endpoint

    # Trigger port forward to ensure local port is open
    _ensure_port_forward(local_port)

    # Final derived URL
    target_url = f"http://localhost:{local_port}{api_path}"

    token = os.environ.get("PLATFORM_AGENT_TOKEN", "your-strong-api-server-key-here")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    conv_id = os.environ.get("AGENT_CONVERSATION_ID", "gke-optimization-session")
    data = {"model": "hermes-agent", "conversation": conv_id, "input": prompt}

    req = urllib.request.Request(
        target_url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST"
    )

    start_time = time.time()
    try:
        # Set a long timeout because agent runs can take several minutes
        # 10 minutes (600 seconds) should be safe
        with urllib.request.urlopen(req, timeout=600) as response:
            latency = time.time() - start_time
            body = response.read().decode("utf-8")
            resp_json = json.loads(body)

            output_text = ""
            trajectory = []
            tools_used = {}

            raw_output = resp_json.get("output", [])
            for part in raw_output:
                part_type = part.get("type")
                if part_type == "message" and part.get("role") == "assistant":
                    content = part.get("content", [])
                    for c in content:
                        if c.get("type") == "output_text":
                            output_text += c.get("text", "")
                elif part_type == "function_call":
                    t_name = part.get("name")
                    t_args = part.get("arguments")
                    if isinstance(t_args, str):
                        try:  # noqa: SIM105
                            t_args = json.loads(t_args)
                        except json.JSONDecodeError:
                            pass
                    trajectory.append({"name": t_name, "args": t_args, "status": "called"})
                    tools_used[t_name] = tools_used.get(t_name, 0) + 1
                elif part_type == "function_call_output":
                    trajectory.append(
                        {
                            "name": part.get("name"),
                            "output": part.get("output"),
                            "status": "response",
                        }
                    )

            # Standardize tokens format
            usage = resp_json.get("usage", {})
            tokens = {
                "input": usage.get("input_tokens", 0),
                "output": usage.get("output_tokens", 0),
                "total": usage.get("total_tokens", 0),
            }

            return {
                "output": output_text,
                "latency": latency,
                "tokens": tokens,
                "tools": tools_used,
                "trajectory": trajectory,
            }

    except urllib.error.HTTPError as e:
        latency = time.time() - start_time
        error_body = e.read().decode("utf-8")
        try:
            err_json = json.loads(error_body)
            error_msg = err_json.get("error", {}).get("message", error_body)
        except json.JSONDecodeError:
            error_msg = error_body
        return {
            "output": f"HTTP Error {e.code}: {error_msg}",
            "latency": latency,
            "tokens": {},
            "tools": {},
            "trajectory": [],
            "skills": [],
        }
    except Exception as e:
        latency = time.time() - start_time
        return {
            "output": f"Error: {str(e)}",
            "latency": latency,
            "tokens": {},
            "tools": {},
            "trajectory": [],
            "skills": [],
        }
