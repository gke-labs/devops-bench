import json
import os
import re
import subprocess
import time
from deepeval.tracing import observe


@observe()
def run_openclaw_agent(prompt, context=None):
    """Runs OpenClaw agent on GCE VM via SSH."""
    ssh_user = os.environ.get("OPENCLAW_SSH_USER", "simrankaurk_google_com")
    vm_host = os.environ.get("OPENCLAW_VM_HOST", "nic0.claw-ubuntu.us-central1-a.c.simrankaurk-gke-dev.internal.gcpnode.com")
    ssh_key = os.environ.get("OPENCLAW_SSH_KEY", "/usr/local/google/home/simrankaurk/.ssh/google_compute_engine")

    # We use --local and --agent main as discovered by the user
    # We also use single quotes for the prompt, assuming it doesn't contain single quotes.
    # For safety, we should escape single quotes if possible, but let's keep it simple first.
    remote_command = f"export NVM_DIR=\"$HOME/.nvm\" && [ -s \"$NVM_DIR/nvm.sh\" ] && source \"$NVM_DIR/nvm.sh\" && ~/bin/openclaw --log-level debug agent --local --agent main -m '{prompt}'"

    ssh_cmd = [
        "ssh",
        "-q",
        "-i",
        ssh_key,
        f"{ssh_user}@{vm_host}",
        remote_command,
    ]

    start_time = time.time()
    try:
        result = subprocess.run(
            ssh_cmd, capture_output=True, text=True, check=True
        )
        latency = time.time() - start_time
        output = result.stdout

        # Parse session file path
        session_file = None
        match = re.search(r"sessionFile=([^ \n]+)", output)
        tokens = {}
        trajectory = []

        if match:
            session_file = match.group(1)
            # Read session file via SSH
            read_cmd = [
                "ssh",
                "-q",
                "-i",
                ssh_key,
                f"{ssh_user}@{vm_host}",
                f"cat {session_file}",
            ]
            try:
                read_result = subprocess.run(
                    read_cmd, capture_output=True, text=True, check=True
                )
                session_content = read_result.stdout

                # Parse session content
                for line in session_content.strip().split("\n"):
                    try:
                        data = json.loads(line)
                        # Extract tokens from assistant message
                        if data.get("type") == "message" and data.get("message", {}).get("role") == "assistant":
                            usage = data.get("message", {}).get("usage")
                            if usage:
                                tokens = usage
                                
                        # Extract trajectory
                        if data.get("type") == "message":
                            msg = data.get("message", {})
                            content = msg.get("content", [])
                            for part in content:
                                if isinstance(part, dict):
                                    if "functionCall" in part:
                                        call = part["functionCall"]
                                        trajectory.append({
                                            "name": call.get("name"),
                                            "args": call.get("args"),
                                            "status": "called"
                                        })
                                    elif "functionResponse" in part:
                                        resp = part["functionResponse"]
                                        trajectory.append({
                                            "name": resp.get("name"),
                                            "output": resp.get("response"),
                                            "status": "response"
                                        })
                    except json.JSONDecodeError:
                        continue
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to read session file: {e.stderr}")

        return {
            "output": output,
            "latency": latency,
            "tokens": tokens,
            "tools": {},
            "trajectory": trajectory,
            "skills": []
        }
    except subprocess.CalledProcessError as e:
        return {
            "output": f"Error: {e.stderr}\nStdout: {e.stdout}",
            "latency": time.time() - start_time,
            "tokens": {},
            "tools": {},
            "trajectory": [],
            "skills": []
        }
