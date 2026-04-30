import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams
from deepeval.tracing import observe
from deepeval.models import DeepEvalBaseLLM
from deepeval.dataset import EvaluationDataset
from google import genai


class GeminiModel(DeepEvalBaseLLM):
    def __init__(self, model_name="gemini-2.5-flash"):
        self.model_name = model_name
        self.client = genai.Client()

    def load_model(self):
        return self.client

    def generate(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.model_name, contents=prompt
        )
        return response.text

    async def a_generate(self, prompt: str) -> str:
        return self.generate(prompt)

    def get_model_name(self):
        return self.model_name


def parse_gemini_cli_output(raw_output: str) -> dict:
    """Parses the JSON output from the Gemini CLI, handling potential log noise."""
    output = raw_output
    tokens = {}
    tools = {}
    
    try:
        match = re.search(r"({.*})", raw_output, re.DOTALL)
        if match:
            json_str = match.group(1)
            data = json.loads(json_str)
            output = data.get("response", raw_output)
            stats = data.get("stats", {})
            
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
        "tools": tools
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
        
        if "-o" in args and "json" in args:
            parsed = parse_gemini_cli_output(output)
            output = parsed["output"]
            tokens = parsed["tokens"]
            tools = parsed["tools"]
                
        return {
            "output": output,
            "latency": latency,
            "tokens": tokens,
            "tools": tools
        }
    except subprocess.CalledProcessError as e:
        return {
            "output": f"Error: {e.stderr}",
            "latency": time.time() - start_time,
            "tokens": {},
            "tools": {}
        }


@observe()
def run_api_agent(model, prompt):
    """Calls Gemini API directly."""
    client = genai.Client()
    start_time = time.time()
    response = client.models.generate_content(model=model, contents=prompt)
    latency = time.time() - start_time
    
    tokens = {}
    if hasattr(response, "usage_metadata"):
        tokens = {
            "input": response.usage_metadata.prompt_token_count,
            "candidates": response.usage_metadata.candidates_token_count,
            "total": response.usage_metadata.total_token_count,
            "cached": getattr(response.usage_metadata, "cached_content_token_count", 0)
        }
        
    return {
        "output": response.text,
        "latency": latency,
        "tokens": tokens,
        "tools": {}
    }


@observe()
def run_mcp_agent(server_addr, prompt):
    """Simulates connection to an MCP server."""
    return f"Executed via MCP server at {server_addr} for prompt: {prompt}"


def replace_placeholders(text, project_id, cluster_name):
    """Replaces project and cluster placeholders in the text."""
    return text.replace("{{PROJECT_ID}}", project_id).replace(
        "{{CLUSTER_NAME}}", cluster_name
    )


def execute_agent(agent_type, agent_target, prompt, context):
    """Executes the appropriate agent and returns standardized results."""
    if agent_type in ["cli", "binary"]:
        return run_cli_agent(agent_target, prompt, context)
    elif agent_type == "api":
        return run_api_agent(agent_target, prompt)
    elif agent_type == "mcp":
        return {
            "output": run_mcp_agent(agent_target, prompt),
            "latency": 0,
            "tokens": {},
            "tools": {},
        }
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")


def create_evaluation_metrics(model):
    outcome_validity = GEval(
        name="OutcomeValidity",
        criteria="Did the agent successfully achieve the DevOps goal?",
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
        ],
        model=model,
    )

    tool_invocation = GEval(
        name="ToolInvocation",
        criteria="The agent should only use tools that are relevant to the user's request.",
        threshold=0.8,
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
        ],
        model=model,
    )

    return [outcome_validity, tool_invocation]


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 evaluate.py <eval_data_json_file>")
        sys.exit(1)

    with open(sys.argv[1], "r") as f:
        eval_data = json.load(f)

    limit = os.environ.get("EVAL_LIMIT")
    if limit and isinstance(eval_data, list):
        eval_data = eval_data[:int(limit)]
        print(f"Limiting evaluation to the first {limit} cases.")

    agent_type = os.environ.get("AGENT_TYPE", "cli").lower()
    agent_target = os.environ.get("AGENT_TARGET", "./my-agent")
    gemini_model = GeminiModel()
    project_id = os.environ.get("PROJECT_ID", "my-project")
    cluster_name = os.environ.get("CLUSTER_NAME", "my-cluster")

    if isinstance(eval_data, list):
        print(f"Running dataset evaluation with {len(eval_data)} cases...")
        dataset = EvaluationDataset()
        test_cases = []
        detailed_results = []

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = f"results/run_{timestamp}"
        os.makedirs(run_dir, exist_ok=True)

        for item in eval_data:
            prompt = item["input"]
            prompt = replace_placeholders(prompt, project_id, cluster_name)

            print(f"Executing agent for prompt: {prompt}")
            
            before_files = set(os.listdir("."))
            
            agent_res = execute_agent(agent_type, agent_target, prompt, {})
                
            after_files = set(os.listdir("."))
            new_files = after_files - before_files
            
            if new_files:
                gen_files_dir = os.path.join(run_dir, "generated_files")
                os.makedirs(gen_files_dir, exist_ok=True)
                for f in new_files:
                    if os.path.isfile(f):
                        shutil.copy(f, os.path.join(gen_files_dir, f))
                        print(f"Stored generated file: {f}")
            
            actual_output = agent_res.get("output", "")
            latency = agent_res.get("latency", 0.0)
            
            detailed_results.append({
                "input": prompt,
                "output": actual_output,
                "latency": latency,
                "tokens": agent_res.get("tokens", {}),
                "tools": agent_res.get("tools", {})
            })

            print(f"--- Agent Response ---\n{actual_output}\n----------------------")

            test_cases.append(
                LLMTestCase(
                    input=prompt,
                    actual_output=actual_output,
                    expected_output=item.get("expected_output", "").replace(
                        "{{PROJECT_ID}}", project_id
                    ),
                    retrieval_context=item.get("retrieval_context", []),
                    latency=latency,
                )
            )
        dataset.test_cases = test_cases

        from deepeval import evaluate

        metrics = create_evaluation_metrics(gemini_model)
        evaluation_result = evaluate(dataset.test_cases, metrics=metrics)
        
        for i, test_result in enumerate(evaluation_result.test_results):
            scores = {}
            for metric_data in test_result.metrics_data:
                scores[metric_data.name] = {
                    "score": metric_data.score,
                    "success": metric_data.success,
                    "reason": getattr(metric_data, "reason", None)
                }
            detailed_results[i]["scores"] = scores
        
        with open(os.path.join(run_dir, "results.json"), "w") as f:
            json.dump(detailed_results, f, indent=2)
        print(f"Results saved to {run_dir}/results.json")

    else:
        # Single task flow (Go integration)
        goal = eval_data["goal"]
        context = eval_data["context"]

        # Replace placeholders in goal if any
        goal = replace_placeholders(goal, project_id, cluster_name)

        agent_res = execute_agent(agent_type, agent_target, goal, context)
        actual_output = agent_res.get("output", "")

        print(f"--- Agent Response ---\n{actual_output}\n----------------------")

        # DeepEval Scoring
        test_case = LLMTestCase(
            input=goal,
            actual_output=actual_output,
            latency=agent_res.get("latency", 0.0)
        )
        metrics = create_evaluation_metrics(gemini_model)
        outcome_validity, tool_invocation = metrics

        outcome_validity.measure(test_case)
        tool_invocation.measure(test_case)

        result = {
            "OutcomeValidityScore": outcome_validity.score,
            "ToolInvocationScore": tool_invocation.score,
            "Passed": outcome_validity.score >= 0.7 and tool_invocation.score >= 0.8,
            "Reason": f"Goal: {outcome_validity.reason}. Tool: {tool_invocation.reason}",
            "Latency": agent_res.get("latency", 0.0),
            "Tokens": agent_res.get("tokens", {}),
            "Tools": agent_res.get("tools", {})
        }
        print(json.dumps(result))


if __name__ == "__main__":
    main()
