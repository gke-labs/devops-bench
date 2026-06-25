import json
import os
import re
import glob
import time
import subprocess
from deepeval.tracing import observe
from pkg.agents.runner.openclaw import run_openclaw_agent, run_openclaw_agent_local
from pkg.agents.runner.kubeagents import run_kubeagents


def parse_gemini_cli_output(raw_output: str) -> dict:
    """Parses the JSON output from the Gemini CLI, handling potential log noise."""
    output = raw_output
    tokens = {}
    tools = {}
    session_id = None
    
    try:
        match = re.search(r"({.*})", raw_output, re.DOTALL)
        if match:
            json_str = match.group(1)
            data = json.loads(json_str)
            output = data.get("response", raw_output)
            stats = data.get("stats", {})
            session_id = data.get("session_id")
            
            models_stats = stats.get("models", {})
            for model_name, model_data in models_stats.items():
                tokens = model_data.get("tokens", {})
                break
                
            tools = stats.get("tools", {})
    except Exception as e:
        print(f"Warning: Failed to parse JSON output from Gemini CLI: {e}")
        
    return {
        "output": output,
        "tokens": tokens,
        "tools": tools,
        "session_id": session_id
    }


def extract_trajectory_from_session(session_id: str) -> dict:
    """Locates and parses the session file for a given session_id to extract trajectory."""
    trajectory = []
    base_dir = os.path.expanduser("~/.gemini/tmp/devops-bench/chats")
    if not os.path.exists(base_dir):
        print(f"Warning: Session directory not found: {base_dir}")
        return {"trajectory": [], "skills": []}
        
    short_id = session_id.split("-")[0] if "-" in session_id else session_id
    pattern = os.path.join(base_dir, f"session-*-{short_id}.jsonl")
    files = glob.glob(pattern)
    
    if not files:
        pattern_rec = os.path.join(base_dir, "**", f"*{short_id}.jsonl")
        files = glob.glob(pattern_rec, recursive=True)

    if not files:
        print(f"Warning: No session file found for session_id: {session_id}")
        return {"trajectory": [], "skills": []}
        
    session_file = files[0]
    print(f"Parsing session file: {session_file}")
    
    referenced_skills = []
    try:
        with open(session_file, "r") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get("type") == "gemini":
                        tool_calls = data.get("toolCalls", [])
                        for call in tool_calls:
                            name = call.get("name")
                            args = call.get("args")
                            status = call.get("status")
                            
                            trajectory.append({
                                "name": name,
                                "args": args,
                                "status": status
                            })
                            
                            # Filter for skills
                            if name == "read_file" and isinstance(args, dict):
                                file_path = args.get("file_path", "")
                                if "skills" in file_path or file_path.endswith("SKILL.md"):
                                    parts = file_path.split("/")
                                    if "skills" in parts:
                                        idx = parts.index("skills")
                                        if idx + 1 < len(parts):
                                            referenced_skills.append(parts[idx+1])
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Warning: Failed to read session file: {e}")
        
    return {
        "trajectory": trajectory,
        "skills": list(set(referenced_skills))
    }


@observe()
def run_cli_agent(agent_target, prompt, context, bench_use_mcp=True, system_instruction=None):
    """Runs an external binary agent."""
    agent_target = os.path.expanduser(agent_target)
    if system_instruction:
        prompt = f"{prompt}\n\nInstructions: {system_instruction}"
    input_data = json.dumps({"goal": prompt, "context": context})
    args = [agent_target]
    use_stdin = True
    if "gemini" in agent_target:
        args.extend(["-o", "json", "--skip-trust"])
        if bench_use_mcp:
            # Pre-approve GKE MCP tools to prevent interactive confirmation prompts in headless mode
            allowed_tools = [
                "mcp_gke_list_clusters",
                "mcp_gke_get_cluster",
                "mcp_gke_generate_manifest",
                "mcp_gke_giq_generate_manifest",
                "mcp_gke_query_logs",
                "mcp_gke_get_log_schema",
                "mcp_gke_get_kubeconfig",
                "mcp_gke_list_namespaces"
            ]
            for tool in allowed_tools:
                args.extend(["--allowed-tools", tool])
        else:
            args.extend(["-e", "none"])
        args.extend(["-p", prompt])
        use_stdin = False
    elif "openclaw" in agent_target or "oc" in agent_target:
        # Which oc agent profile to run (`oc agent --agent <name>`). Defaults to
        # "main" (modern openclaw's default agent id; older builds used "operator").
        # Override with OPENCLAW_AGENT. Matches the refactored arm's default so the
        # two arms target the same profile unless explicitly told otherwise.
        oc_agent = (os.environ.get("OPENCLAW_AGENT") or "main").strip() or "main"
        # When the agent, harness, and (kind) cluster are co-located on one host,
        # run oc locally instead of SSHing to the GCE VM.
        if os.environ.get("OPENCLAW_LOCAL", "false").lower() == "true":
            return run_openclaw_agent_local(prompt, context, agent_name=oc_agent)
        return run_openclaw_agent(prompt, context, agent_name=oc_agent)
    elif "kubeagents" in agent_target:
        return run_kubeagents(prompt, _context=context)
        
    start_time = time.time()
    
    # Disable OTLP telemetry exporters to prevent hangs from broken telemetry endpoints
    env = os.environ.copy()
    
    # Map benchmark standardized vars to Gemini CLI expected vars
    if "AGENT_API_KEY" in env:
        env["GOOGLE_API_KEY"] = env["AGENT_API_KEY"]
        env["GEMINI_API_KEY"] = env["AGENT_API_KEY"]
    if "AGENT_MODEL" in env:
        env["GEMINI_MODEL"] = env["AGENT_MODEL"]

    env["OTEL_TRACES_EXPORTER"] = "none"
    env["OTEL_METRICS_EXPORTER"] = "none"
    env["OTEL_LOGS_EXPORTER"] = "none"
    env["OTEL_SDK_DISABLED"] = "true"

    try:
        if use_stdin:
            result = subprocess.run(
                args,
                input=input_data,
                text=True,
                capture_output=True,
                check=True,
                env=env,
            )
        else:
            result = subprocess.run(
                args,
                text=True,
                capture_output=True,
                check=True,
                env=env,
            )
        latency = time.time() - start_time
        
        output = result.stdout
        tokens = {}
        tools = {}
        trajectory = []
        skills = []
        
        if "-o" in args and "json" in args:
            parsed = parse_gemini_cli_output(output)
            output = parsed["output"]
            tokens = parsed["tokens"]
            tools = parsed["tools"]
            session_id = parsed.get("session_id")
            
            if session_id:
                res = extract_trajectory_from_session(session_id)
                trajectory = res.get("trajectory", [])
                skills = res.get("skills", [])
                
        return {
            "output": output,
            "latency": latency,
            "tokens": tokens,
            "tools": tools,
            "trajectory": trajectory,
            "skills": skills
        }
    except subprocess.CalledProcessError as e:
        return {
            "output": f"Error: {e.stderr}",
            "latency": time.time() - start_time,
            "tokens": {},
            "tools": {},
            "trajectory": [],
            "skills": []
        }
