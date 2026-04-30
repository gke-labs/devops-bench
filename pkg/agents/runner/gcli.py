import json
import os
import re
import glob
import time
import subprocess
from deepeval.tracing import observe


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
def run_cli_agent(bin_path, prompt, context):
    """Runs an external binary agent."""
    input_data = json.dumps({"goal": prompt, "context": context})
    args = [bin_path]
    use_stdin = True
    if "gemini" in bin_path:
        args.extend(["-o", "json", "-p", prompt])
        use_stdin = False
        
    start_time = time.time()
    try:
        if use_stdin:
            result = subprocess.run(
                args,
                input=input_data,
                text=True,
                capture_output=True,
                check=True,
            )
        else:
            result = subprocess.run(
                args,
                text=True,
                capture_output=True,
                check=True,
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
