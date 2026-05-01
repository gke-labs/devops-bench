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

from pkg.agents.runner.api.llm_adapters import AnthropicClientAdapter, GeminiClientAdapter
from pkg.agents.runner.api.api import run_api_agent
from pkg.agents.runner.gcli import run_cli_agent
from pkg.evaluator.loader import load_from_tasks_dir, load_outcome_rubric, load_tool_rubric


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
        model=self.model_name, contents=prompt
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





def load_configuration_context():
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

    provider = os.environ.get("PROVIDER", "N/A")
    use_mcp = os.environ.get("USE_MCP", "false")
    mcp_path = os.environ.get("MCP_SERVER_PATH", "N/A")

    print(f"  - Provider:       {provider.upper()}")
    print(f"  - Use MCP:        {use_mcp.lower()}")
    print(f"  - MCP Server:     {mcp_path}")
    print("-" * 50)

    return agent_type, agent_target, gemini_model, project_id, cluster_name


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 evaluate.py <tasks_directory>")
        sys.exit(1)

    input_path = sys.argv[1]
    
    if os.path.isdir(input_path):
        print(f"Loading tasks specifications dynamically from {input_path} folder...")
        eval_data = load_from_tasks_dir(input_path)
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

    agent_type, agent_target, gemini_model, project_id, cluster_name = load_configuration_context()

    print(f"Running dataset evaluation with {len(eval_data)} cases...")
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
        trajectory = agent_res.get("trajectory", [])

        # Load skill descriptions dynamically and interpolate values
        outcome_rubric = load_outcome_rubric(prompt, actual_output, item.get("expected_output", ""), project_id)
        tool_rubric = load_tool_rubric(prompt, trajectory, item)

        outcome_validity = GEval(
            name="OutcomeValidity",
            criteria=outcome_rubric,
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
            ],
            model=gemini_model,
        )

        tool_invocation = GEval(
            name="ToolInvocation",
            criteria=tool_rubric,
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
            ],
            model=gemini_model,
        )

        test_case = LLMTestCase(
            input=prompt,
            actual_output=actual_output,
            expected_output=item.get("expected_output", "").replace(
                "{{PROJECT_ID}}", project_id
            ),
            retrieval_context=item.get("retrieval_context", []),
            latency=latency,
        )

        tool_test_case = LLMTestCase(
            input=prompt,
            actual_output=json.dumps(trajectory, indent=2) if trajectory else "None (zero tools recorded)",
            expected_output="N/A",
            latency=latency,
        )

        print(f"Evaluating individual task criteria judge scores for: {item['name']}...")
        outcome_result = evaluate([test_case], metrics=[outcome_validity])
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

        detailed_results.append({
            "input": prompt,
            "output": actual_output,
            "latency": latency,
            "tokens": agent_res.get("tokens", {}),
            "tools": agent_res.get("tools", {}),
            "trajectory": trajectory,
            "skills": agent_res.get("skills", []),
            "scores": scores
        })

    with open(os.path.join(run_dir, "results.json"), "w") as f:
        json.dump(detailed_results, f, indent=2)
    print(f"Results saved to {run_dir}/results.json")
    
    print("\n=== Detailed Results ===")
    print(json.dumps(detailed_results, indent=2))
    print("=========================")


if __name__ == "__main__":
    main()
