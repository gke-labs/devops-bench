import os
import sys
import yaml


def safe_parse_yaml(content: str) -> dict:
    return yaml.safe_load(content) or {}


def parse_documentation_from_yaml(content: str) -> list:
    """Parses the custom documentation list from YAML text."""
    docs = []
    lines = content.splitlines()
    in_doc_section = False
    current_doc = None
    current_constraint = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if line.startswith("documentation:"):
            in_doc_section = True
            continue

        indent = len(line) - len(line.lstrip())
        if in_doc_section:
            if indent == 0 and not line.startswith("-"):
                in_doc_section = False
                continue

            if stripped.startswith("- doc_name:"):
                if current_doc:
                    docs.append(current_doc)
                name = stripped.split("doc_name:", 1)[1].strip().strip('"').strip("'")
                current_doc = {"doc_name": name, "url": "", "constraints": []}
            elif stripped.startswith("url:"):
                if current_doc:
                    url = stripped.split("url:", 1)[1].strip().strip('"').strip("'")
                    current_doc["url"] = url
            elif stripped.startswith("constraints:"):
                continue
            elif stripped.startswith("- text:"):
                if current_doc:
                    text = stripped.split("text:", 1)[1].strip().strip('"').strip("'")
                    current_constraint = {"text": text, "critical": False}
                    current_doc["constraints"].append(current_constraint)
            elif stripped.startswith("critical:"):
                if current_constraint:
                    crit_val = stripped.split("critical:", 1)[1].strip().lower()
                    current_constraint["critical"] = crit_val == "true"

    if current_doc:
        docs.append(current_doc)

    return docs


def load_from_tasks_dir(dir_path: str) -> list:
    eval_data = []

    if not os.path.exists(dir_path):
        print(f"Error: tasks directory not found at {dir_path}")
        sys.exit(1)

    for root, dirs, files in os.walk(dir_path):
        # Sort dirs in place to ensure deterministic ordering during walk
        dirs.sort()
        if "task.yaml" in files:
            yaml_path = os.path.join(root, "task.yaml")
            try:
                with open(yaml_path, "r") as stream:
                    yaml_text = stream.read()
                    content = safe_parse_yaml(yaml_text)
                    docs = parse_documentation_from_yaml(yaml_text)
                    if isinstance(content, dict):
                        task_id = content.get("task_id")
                        name = content.get("name", os.path.basename(root))
                        prompt = content.get("prompt", "")
                        expected = content.get("expected_output", "")
                        retrieval = content.get("retrieval_context", [])
                        chaos_spec = content.get("chaos_spec")
                        verification_spec = content.get("verification_spec")

                        eval_data.append(
                            {
                                "task_id": task_id if task_id is not None else 999,
                                "name": name,
                                "input": prompt.strip()
                                if isinstance(prompt, str)
                                else str(prompt),
                                "expected_output": expected.strip()
                                if isinstance(expected, str)
                                else str(expected),
                                "retrieval_context": retrieval
                                if isinstance(retrieval, list)
                                else [],
                                "chaos_spec": chaos_spec,
                                "verification_spec": verification_spec,
                                "infrastructure": content.get("infrastructure", {}),
                                "documentation": docs,
                            }
                        )
            except Exception as e:
                print(f"Warning: Failed to read task spec in {yaml_path}: {e}")

    eval_data.sort(key=lambda k: k["task_id"])
    return eval_data

