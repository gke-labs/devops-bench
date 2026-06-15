import json
import os
import re
import shlex
import subprocess
import time
import getpass
from deepeval.tracing import observe


# OpenClaw emits ANSI-colored debug logs to stdout. The escape codes corrupt the
# `sessionFile=...` path extraction (the regex would capture the trailing reset
# code) and add noise to the text the judge grades, so strip them first.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text):
    return _ANSI_RE.sub("", text)


def _parse_openclaw_session(session_content):
    """Parses an OpenClaw session JSONL into (tokens, trajectory)."""
    tokens = {}
    trajectory = []
    for line in session_content.strip().split("\n"):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

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
                if not isinstance(part, dict):
                    continue
                if "functionCall" in part:
                    call = part["functionCall"]
                    trajectory.append({
                        "name": call.get("name"),
                        "args": call.get("args"),
                        "status": "called"
                    })
                elif part.get("type") == "toolCall":
                    trajectory.append({
                        "name": part.get("name"),
                        "args": part.get("arguments"),
                        "status": "called"
                    })
                elif "functionResponse" in part:
                    resp = part["functionResponse"]
                    trajectory.append({
                        "name": resp.get("name"),
                        "output": resp.get("response"),
                        "status": "response"
                    })

    return tokens, trajectory


@observe()
def run_openclaw_agent(prompt, context=None, agent_name="main"):
    """Runs OpenClaw agent on GCE VM via SSH."""
    current_user = getpass.getuser()
    project_id = os.environ.get("GCP_PROJECT_ID", "simrankaurk-gke-dev")

    ssh_user = os.environ.get("OPENCLAW_SSH_USER", f"{current_user}_google_com")
    vm_host = os.environ.get("OPENCLAW_VM_HOST", f"nic0.claw-ubuntu.us-central1-a.c.{project_id}.internal.gcpnode.com")
    ssh_key = os.environ.get("OPENCLAW_SSH_KEY", os.path.expanduser("~/.ssh/google_compute_engine"))

    # We use --local and --agent as discovered by the user
    # We also use single quotes for the prompt, assuming it doesn't contain single quotes.
    # For safety, we should escape single quotes if possible, but let's keep it simple first.
    remote_command = f"rm -rf ~/.openclaw/agents/operator/sessions/* && export NVM_DIR=\"$HOME/.nvm\" && [ -s \"$NVM_DIR/nvm.sh\" ] && source \"$NVM_DIR/nvm.sh\" && ~/bin/oc --log-level debug agent --local --agent {agent_name} -m '{prompt}'"

    ssh_cmd = [
        "ssh",
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
        output = _strip_ansi(result.stdout)

        # Parse session file path
        match = re.search(r"sessionFile=([^ \n]+)", output)
        tokens = {}
        trajectory = []

        if match:
            session_file = match.group(1)
            # Read session file via SSH
            read_cmd = [
                "ssh",
                "-i",
                ssh_key,
                f"{ssh_user}@{vm_host}",
                f"cat {session_file}",
            ]
            try:
                read_result = subprocess.run(
                    read_cmd, capture_output=True, text=True, check=True
                )
                tokens, trajectory = _parse_openclaw_session(read_result.stdout)
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


@observe()
def run_openclaw_agent_local(prompt, context=None, agent_name="operator"):
    """Runs OpenClaw agent locally via subprocess (no SSH).

    Used when the harness, the kind cluster, and the agent are co-located on the
    same host (e.g. running the eval directly on the runner VM). Selected by
    setting OPENCLAW_LOCAL=true. The SSH-based runner remains the default.
    """
    oc_bin = os.environ.get("OPENCLAW_BIN", os.path.expanduser("~/bin/oc"))
    sessions_glob = os.path.expanduser(f"~/.openclaw/agents/{agent_name}/sessions")

    # Mirror the remote command: clear prior sessions, load nvm, run the agent.
    # shlex.quote everything interpolated into the shell string — prompts contain
    # single quotes and newlines, which would otherwise break shell parsing.
    local_command = (
        f"rm -rf {shlex.quote(sessions_glob)}/* 2>/dev/null; "
        "export NVM_DIR=\"$HOME/.nvm\"; [ -s \"$NVM_DIR/nvm.sh\" ] && . \"$NVM_DIR/nvm.sh\"; "
        f"{shlex.quote(oc_bin)} --log-level debug agent --local "
        f"--agent {shlex.quote(agent_name)} -m {shlex.quote(prompt)}"
    )

    start_time = time.time()
    try:
        result = subprocess.run(
            local_command,
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            check=True,
        )
        latency = time.time() - start_time
        output = _strip_ansi(result.stdout)

        match = re.search(r"sessionFile=([^ \n]+)", output)
        tokens = {}
        trajectory = []

        if match:
            session_file = os.path.expanduser(match.group(1))
            try:
                with open(session_file, "r") as f:
                    tokens, trajectory = _parse_openclaw_session(f.read())
            except OSError as e:
                print(f"Warning: Failed to read local session file {session_file}: {e}")

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
