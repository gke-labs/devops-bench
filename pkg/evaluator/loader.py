import os
import sys
import json
import re

def safe_parse_yaml(content: str) -> dict:
    """Extracts simple structural elements of YAML definitions without library imports."""
    lines = content.splitlines()
    result = {}
    current_key = None
    in_scalar = False
    scalar_val = []
    indent_level = None
    
    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            if in_scalar:
                scalar_val.append("")
            continue
            
        indent = len(stripped) - len(stripped.lstrip())
        
        if in_scalar:
            if indent_level is None:
                indent_level = indent
                
            if indent >= indent_level:
                scalar_val.append(stripped[indent_level:])
                continue
            else:
                result[current_key] = "\n".join(scalar_val).strip()
                in_scalar = False
                scalar_val = []
                current_key = None
                indent_level = None
                
        if ":" in stripped:
            parts = stripped.split(":", 1)
            key = parts[0].strip()
            val = parts[1].strip()
            
            if val == "|":
                current_key = key
                in_scalar = True
                scalar_val = []
                indent_level = None
            else:
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                try:
                    if val.isdigit():
                        val = int(val)
                except ValueError:
                    pass
                result[key] = val
                
    if current_key and scalar_val:
        result[current_key] = "\n".join(scalar_val).strip()
        
    return result


def load_from_tasks_dir(dir_path: str) -> list:
    eval_data = []
    
    if not os.path.exists(dir_path):
        print(f"Error: tasks directory not found at {dir_path}")
        sys.exit(1)
        
    for item in sorted(os.listdir(dir_path)):
        sub_dir = os.path.join(dir_path, item)
        if os.path.isdir(sub_dir):
            yaml_path = os.path.join(sub_dir, "task.yaml")
            if os.path.exists(yaml_path):
                try:
                    with open(yaml_path, "r") as stream:
                        yaml_text = stream.read()
                        content = safe_parse_yaml(yaml_text)
                        if isinstance(content, dict):
                            task_id = content.get("task_id")
                            name = content.get("name", item)
                            prompt = content.get("prompt", "")
                            expected = content.get("expected_output", "")
                            retrieval = content.get("retrieval_context", [])
                            
                            eval_data.append({
                                "task_id": task_id if task_id is not None else 999,
                                "name": name,
                                "input": prompt.strip() if isinstance(prompt, str) else str(prompt),
                                "expected_output": expected.strip() if isinstance(expected, str) else str(expected),
                                "retrieval_context": retrieval if isinstance(retrieval, list) else []
                            })
                except Exception as e:
                    print(f"Warning: Failed to read task spec in {yaml_path}: {e}")
                    
    eval_data.sort(key=lambda k: k["task_id"])
    return eval_data


def load_outcome_rubric(prompt: str, response: str, expected_output: str, project_id: str) -> str:
    try:
        with open("skills/outcome-validity-skill.md", "r") as f:
            rubric = f.read()
    except FileNotFoundError:
        return f"Evaluate if response satisfies objective '{prompt}'. Validate expectations: {expected_output}"

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", rubric, re.DOTALL)
    if match:
        rubric = rubric[match.end():]

    critical_facts = expected_output
    golden_manifest = "N/A, not specified"

    if "Expected Manifest Generated:" in expected_output:
        parts = expected_output.split("Expected Manifest Generated:", 1)
        critical_facts = parts[0].strip()
        golden_manifest = parts[1].strip()

    rubric = rubric.replace("{{ golden_manifest }}", golden_manifest)
    rubric = rubric.replace("{{ critical_facts }}", critical_facts)

    print(f"\n[DEBUG] Generated Outcome Validity Rubric: \n{rubric}\n[DEBUG END]")
    return rubric


def load_tool_rubric(prompt: str, trajectory: list, task_item: dict) -> str:
    try:
        with open("skills/tool-invocation-skill.md", "r") as f:
            rubric = f.read()
    except FileNotFoundError:
        return f"Evaluate tool execution efficiency against prompt objective: '{prompt}'."

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", rubric, re.DOTALL)
    if match:
        rubric = rubric[match.end():]

    execution_trace = json.dumps(trajectory, indent=2) if trajectory else "None (zero tools recorded)"
    
    golden_tools_list = task_item.get("golden_tools", [])
    golden_tools = ", ".join(golden_tools_list) if golden_tools_list else "N/A (no predefined critical tool sequence constraints)"

    rubric = rubric.replace("{{ execution_trace }}", execution_trace)
    rubric = rubric.replace("{{ golden_tools }}", golden_tools)

    print(f"\n[DEBUG] Generated Tool Invocation Rubric: \n{rubric}\n[DEBUG END]")
    return rubric
