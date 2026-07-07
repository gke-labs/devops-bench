import json
import os
import re
import shlex
import subprocess
import tempfile
import time
import getpass
from deepeval.tracing import observe


# OpenClaw emits ANSI-colored debug logs to stdout. The escape codes corrupt the
# `sessionFile=...` path extraction (the regex would capture the trailing reset
# code) and add noise to the text the judge grades, so strip them first.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Default oc agent profile (override with OPENCLAW_AGENT) and shared config path.
_DEFAULT_AGENT_NAME = "main"
_DEFAULT_CONFIG_PATH = "~/.openclaw/openclaw.json"


def _strip_ansi(text):
    return _ANSI_RE.sub("", text)


def _resolve_agent_name(explicit):
    """Pick the oc agent profile: explicit arg, OPENCLAW_AGENT env, then 'main'."""
    return explicit or os.environ.get("OPENCLAW_AGENT") or _DEFAULT_AGENT_NAME


def _oc_model_id():
    """Resolve the OpenClaw model id from the harness env (AGENT_MODEL/AGENT_PROVIDER).

    The model is passed per-run via ``oc agent --model`` (see `_oc_model_flag`),
    not the global `oc models set`. Returns oc's 'provider/model' id (e.g.
    'google/gemini-3.1-pro-preview'), or "" when AGENT_MODEL is unset (oc's
    configured default is then left untouched — preserving prior behavior).
    """
    model = os.environ.get("AGENT_MODEL", "").strip()
    if not model:
        return ""
    if "/" not in model:  # allow AGENT_MODEL to be a full oc id (provider/model)
        provider = (os.environ.get("AGENT_PROVIDER") or "google").strip().lower()
        if provider == "gemini":
            provider = "google"
        model = f"{provider}/{model}"
    return model


def _oc_model_flag():
    """Return ``--model <id> `` for ``oc agent``, or "" when AGENT_MODEL is unset.

    The model is selected per-run via ``oc agent --model`` (not the global
    ``oc models set``), so nothing mutates the shared oc config — concurrent
    runs neither race on it nor pollute each other's default model.
    """
    model_id = _oc_model_id()
    if not model_id:
        return ""
    return f"--model {shlex.quote(model_id)} "


def _accumulate_usage(acc, usage):
    """Sum one turn's token usage into a running accumulator, in place.

    OpenClaw reports ``usage`` per assistant message (i.e. per model call), so
    the session total is the sum across every turn, not the value from any single
    turn. Numeric fields are added; nested mappings (e.g. a ``cost`` breakdown)
    are summed recursively. Booleans and other non-numeric values are ignored.

    Args:
        acc: Accumulator mutated in place.
        usage: A single turn's usage mapping.
    """
    for key, value in usage.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            acc[key] = acc.get(key, 0) + value
        elif isinstance(value, dict):
            nested = acc.setdefault(key, {})
            if isinstance(nested, dict):
                _accumulate_usage(nested, value)


def _parse_openclaw_session(session_content):
    """Parses an OpenClaw session JSONL into (tokens, trajectory).

    ``tokens`` is the usage summed across all assistant turns; taking only the
    last turn (as a prior version did) undercounts a multi-turn session to a
    single model call.
    """
    tokens = {}
    trajectory = []
    for line in session_content.strip().split("\n"):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Accumulate token usage across every assistant message (per-turn usage).
        if data.get("type") == "message" and data.get("message", {}).get("role") == "assistant":
            usage = data.get("message", {}).get("usage")
            if isinstance(usage, dict):
                _accumulate_usage(tokens, usage)

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
def run_openclaw_agent(prompt, context=None, agent_name=None):
    """Runs OpenClaw agent on GCE VM via SSH."""
    current_user = getpass.getuser()
    project_id = os.environ.get("GCP_PROJECT_ID", "simrankaurk-gke-dev")
    agent_name = _resolve_agent_name(agent_name)

    ssh_user = os.environ.get("OPENCLAW_SSH_USER", f"{current_user}_google_com")
    vm_host = os.environ.get("OPENCLAW_VM_HOST", f"nic0.claw-ubuntu.us-central1-a.c.{project_id}.internal.gcpnode.com")
    ssh_key = os.environ.get("OPENCLAW_SSH_KEY", os.path.expanduser("~/.ssh/google_compute_engine"))

    # Parallel isolation: when RUN_ID is set, isolate the remote oc state
    # (sessions/memory/commitments) per run via a remote OPENCLAW_STATE_DIR while
    # sharing OPENCLAW_CONFIG_PATH; the empty state dir needs no session wipe.
    run_id = os.environ.get("RUN_ID")
    if run_id:
        safe = re.sub(r"[^A-Za-z0-9_-]", "-", run_id)
        remote_config = os.environ.get("OPENCLAW_CONFIG_PATH") or "$HOME/.openclaw/openclaw.json"
        setup = (
            f'export OPENCLAW_STATE_DIR="$HOME/.openclaw-runs/{safe}/openclaw-state" '
            f'OPENCLAW_CONFIG_PATH="{remote_config}" && '
        )
    else:
        setup = "rm -rf ~/.openclaw/agents/" + shlex.quote(agent_name) + "/sessions/* && "

    # We use --local and --agent as discovered by the user
    # We also use single quotes for the prompt, assuming it doesn't contain single quotes.
    # For safety, we should escape single quotes if possible, but let's keep it simple first.
    model_flag = _oc_model_flag()
    remote_command = f"{setup}export NVM_DIR=\"$HOME/.nvm\" && [ -s \"$NVM_DIR/nvm.sh\" ] && source \"$NVM_DIR/nvm.sh\" && ~/bin/oc --log-level debug agent --local --agent {agent_name} {model_flag}-m '{prompt}'"

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
def run_openclaw_agent_local(prompt, context=None, agent_name=None):
    """Runs OpenClaw agent locally via subprocess (no SSH).

    Used when the harness, the kind cluster, and the agent are co-located on the
    same host (e.g. running the eval directly on the runner VM). Selected by
    setting OPENCLAW_LOCAL=true. The SSH-based runner remains the default.

    Parallel isolation: when RUN_ID is set, the run gets its own
    OPENCLAW_STATE_DIR (isolated sessions/memory/commitments) while sharing
    OPENCLAW_CONFIG_PATH; the empty state dir needs no session wipe and the
    model is selected per-run with ``oc agent --model``.
    """
    agent_name = _resolve_agent_name(agent_name)
    oc_bin = os.environ.get("OPENCLAW_BIN", os.path.expanduser("~/bin/oc"))
    sessions_glob = os.path.expanduser(f"~/.openclaw/agents/{agent_name}/sessions")

    run_id = os.environ.get("RUN_ID")
    isolation_env = {}
    wipe_frag = f"rm -rf {shlex.quote(sessions_glob)}/* 2>/dev/null; "
    if run_id:
        base = os.environ.get("BENCH_RUN_DIR") or os.path.join(
            tempfile.gettempdir(), "devops-bench-runs", run_id
        )
        isolation_env = {
            "OPENCLAW_STATE_DIR": os.path.join(base, "openclaw-state"),
            "OPENCLAW_CONFIG_PATH": os.path.expanduser(
                os.environ.get("OPENCLAW_CONFIG_PATH") or _DEFAULT_CONFIG_PATH
            ),
        }
        wipe_frag = ""  # isolated state dir starts empty

    # Mirror the remote command: load nvm, run the agent. shlex.quote everything
    # interpolated into the shell string — prompts contain single quotes and
    # newlines, which would otherwise break shell parsing.
    local_command = (
        f"{wipe_frag}"
        "export NVM_DIR=\"$HOME/.nvm\"; [ -s \"$NVM_DIR/nvm.sh\" ] && . \"$NVM_DIR/nvm.sh\"; "
        f"{shlex.quote(oc_bin)} --log-level debug agent --local "
        f"--agent {shlex.quote(agent_name)} {_oc_model_flag()}-m {shlex.quote(prompt)}"
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
            env={**os.environ, **isolation_env} if isolation_env else None,
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
