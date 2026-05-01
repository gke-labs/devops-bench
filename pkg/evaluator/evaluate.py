import asyncio
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from deepeval import assert_test, evaluate
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams
from deepeval.tracing import observe
from deepeval.models import DeepEvalBaseLLM
from deepeval.dataset import EvaluationDataset
from google import genai

# Ensure module imports resolve locally
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../pkg/agents/runner/api")))

from pkg.agents.runner.api.llm_adapters import AnthropicClientAdapter, GeminiClientAdapter

from pkg.agents.runner.api.api import run_api_agent
from pkg.agents.runner.gcli import run_cli_agent
from pkg.evaluator.loader import load_from_tasks_dir, safe_parse_yaml


class GeminiDeepEvalModel(DeepEvalBaseLLM):
  """Wrapper for Gemini SDK to be used with DeepEval."""

  def __init__(self, model_name="gemini-2.5-flash"):
    self.model_name = model_name
    project_id = os.environ.get("VERTEX_PROJECT_ID")
    location = os.environ.get("VERTEX_LOCATION", "us-central1")
    
    if project_id:
      self.client = genai.Client(
          vertexai=True, project=project_id, location=location
      )
    else:
      self.client = genai.Client()

  def load_model(self):
    return self.client

  def generate(self, prompt: str) -> str:
    response = self.client.models.generate_content(
        model=self.model_name,
        contents=prompt,
    )
    return response.text

  async def a_generate(self, prompt: str) -> str:
    return self.generate(prompt)

  def get_model_name(self):
    return self.model_name


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
        mcp_server_path = os.environ.get("MCP_SERVER_PATH", "./gke-mcp")
        provider = os.environ.get("PROVIDER", "gemini")
        if provider == "gemini":
            llm_client = GeminiClientAdapter()
        elif provider == "anthropic":
            llm_client = AnthropicClientAdapter()
        else:
            print(f"Unknown provider: {provider}")
        use_mcp_env = os.environ.get("USE_MCP", "true").lower()
        use_mcp = use_mcp_env == "true"
        return asyncio.run(run_api_agent(prompt, mcp_server_path, llm_client, use_mcp=use_mcp))
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")


def create_evaluation_metrics(model):
    with open("skills/outcome-validity-skill.md", "r") as f:
        outcome_criteria = f.read()

    with open("skills/tool-invocation-skill.md", "r") as f:
        tool_criteria = f.read()

    outcome_validity = GEval(
        name="OutcomeValidity",
        criteria=outcome_criteria,
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
        ],
        model=model,
    )

    tool_invocation = GEval(
        name="ToolInvocation",
        criteria=tool_criteria,
        threshold=0.8,
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
        ],
        model=model,
    )

    return [outcome_validity, tool_invocation]


def evaluate_metrics_batch(detailed_results, project_id, gemini_model):
    """Calculates batch metrics for a list of execution results."""
    print("\nStarting batch post-processing evaluation metrics...")
    for res in detailed_results:
        prompt = res["input"]
        actual_output = res["output"]
        trajectory = res["trajectory"]
        expected_output_raw = res["expected_output_raw"]
        latency = res["latency"]
        name = res["name"]
        retrieval_context = res["retrieval_context"]

        metrics = create_evaluation_metrics(gemini_model)
        outcome_criteria = metrics[0].criteria
        tool_criteria = metrics[1].criteria

        outcome_validity = GEval(
            name="OutcomeValidity",
            criteria=outcome_criteria,
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
            ],
            model=gemini_model,
        )

        tool_invocation = GEval(
            name="ToolInvocation",
            criteria=tool_criteria,
            threshold=0.8,
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
            ],
            model=gemini_model,
        )

        outcome_test_case = LLMTestCase(
            input=prompt,
            actual_output=actual_output if actual_output else "No response generated",
            expected_output=expected_output_raw.replace("{{PROJECT_ID}}", project_id),
            retrieval_context=retrieval_context,
            latency=latency,
        )

        combined_actual = {
            "tools_used": res.get("tools", []),
            "execution_trace": trajectory
        }
        tool_test_case = LLMTestCase(
            input=prompt,
            actual_output=json.dumps(combined_actual, indent=2),
            expected_output=expected_output_raw.replace("{{PROJECT_ID}}", project_id),
            latency=latency,
        )

        print(f"Evaluating metrics for: {name}...")
        outcome_result = evaluate([outcome_test_case], metrics=[outcome_validity])
        tool_result = evaluate([tool_test_case], metrics=[tool_invocation])

        scores = {}
        for test_result in outcome_result.test_results:
            for metric_data in test_result.metrics_data:
                scores[metric_data.name] = {
                    "score": metric_data.score,
                    "success": metric_data.success,
                    "reason": getattr(metric_data, "reason", None)
                }
        for test_result in tool_result.test_results:
            for metric_data in test_result.metrics_data:
                scores[metric_data.name] = {
                    "score": metric_data.score,
                    "success": metric_data.success,
                    "reason": getattr(metric_data, "reason", None)
                }

        res["scores"] = scores


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 evaluate.py <tasks_directory>")
        sys.exit(1)

    input_path = sys.argv[1]
    
    if os.path.isdir(input_path):
        print(f"Loading tasks specifications dynamically from {input_path} folder...")
        eval_data = load_from_tasks_dir(input_path)
    elif input_path.endswith((".yaml", ".yml")):
        print(f"Loading task specification from {input_path}...")
        with open(input_path, "r") as f:
            content = safe_parse_yaml(f.read())
            eval_data = [{
                "task_id": content.get("task_id", 1),
                "name": content.get("name", "Legacy Case"),
                "input": content.get("prompt", "").strip(),
                "expected_output": content.get("expected_output", "").strip(),
                "retrieval_context": content.get("retrieval_context", [])
            }]
    else:
        with open(input_path, "r") as f:
            eval_data = json.load(f)

    if isinstance(eval_data, dict):
        eval_data = [{
            "task_id": eval_data.get("task_id", 1),
            "name": eval_data.get("name", "Legacy Case"),
            "input": eval_data.get("goal", eval_data.get("input", "")),
            "expected_output": eval_data.get("expected_output", ""),
            "retrieval_context": eval_data.get("retrieval_context", [])
        }]

    limit = os.environ.get("EVAL_LIMIT")
    if limit and isinstance(eval_data, list):
        eval_data = eval_data[:int(limit)]
        print(f"Limiting evaluation to the first {limit} cases.")

    agent_type = os.environ.get("AGENT_TYPE", "cli").lower()
    agent_target = os.environ.get("AGENT_TARGET", "./my-agent")
    gemini_model = GeminiDeepEvalModel()
    project_id = os.environ.get("PROJECT_ID", "my-project")
    cluster_name = os.environ.get("CLUSTER_NAME", "my-cluster")

    print("-" * 50)
    print("Configuration Context:")
    print(f"  - Agent Type:     {agent_type.upper()}")
    print(f"  - Agent Target:   {agent_target}")
    print(f"  - Project ID:     {project_id}")
    print(f"  - Cluster Name:   {cluster_name}")
    print("-" * 50)

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
            "tools": agent_res.get("tools", {}),
            "trajectory": agent_res.get("trajectory", []),
            "skills": agent_res.get("skills", [])
        })

        print(f"--- Agent Response ---\n{actual_output}\n----------------------")

        detailed_results[-1]["expected_output_raw"] = item.get("expected_output", "")
        detailed_results[-1]["name"] = item["name"]
        detailed_results[-1]["retrieval_context"] = item.get("retrieval_context", [])

    # Save tasks execution outputs immediately
    with open(os.path.join(run_dir, "results.json"), "w") as f:
        json.dump(detailed_results, f, indent=2)
    print(f"Execution complete. Results safely saved to {run_dir}/results.json")

    # 2. Loop to EVALUATE metrics for all tasks at the end
    # 2. Execute batch metrics post-processing turn via helper function
    evaluate_metrics_batch(detailed_results, project_id, gemini_model)

    with open(os.path.join(run_dir, "results.json"), "w") as f:
        json.dump(detailed_results, f, indent=2)
    print(f"Post-processing evaluation complete. Updated results saved to {run_dir}/results.json")
    
    print("\n=== Detailed Results ===")
    print(json.dumps(detailed_results, indent=2))
    print("=========================")


if __name__ == "__main__":
    main()
