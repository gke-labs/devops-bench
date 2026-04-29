import json
import os
import subprocess
import sys
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


# --- AGENT EXECUTORS ---
@observe()
def run_cli_agent(bin_path, prompt, context):
    """Runs an external binary agent."""
    input_data = json.dumps({"goal": prompt, "context": context})
    try:
        result = subprocess.run(
            [bin_path],
            input=input_data,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr}"


@observe()
def run_api_agent(model, prompt):
    """Calls Gemini API directly."""
    client = genai.Client()
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text


@observe()
def run_mcp_agent(server_addr, prompt):
    """Simulates connection to an MCP server."""
    return f"Executed via MCP server at {server_addr} for prompt: {prompt}"


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


# --- MAIN EXECUTION ---
def main():
    if len(sys.argv) < 2:
        print("Usage: python3 evaluate.py <eval_data_json_file>")
        sys.exit(1)

    with open(sys.argv[1], "r") as f:
        eval_data = json.load(f)

    agent_type = os.environ.get("AGENT_TYPE", "cli").lower()
    agent_target = os.environ.get("AGENT_TARGET", "./my-agent")
    gemini_model = GeminiModel()

    # Get project and cluster from env or use defaults for replacement
    project_id = os.environ.get("PROJECT_ID", "my-project")
    cluster_name = os.environ.get("CLUSTER_NAME", "my-cluster")

    if isinstance(eval_data, list):
        print(f"Running dataset evaluation with {len(eval_data)} cases...")
        dataset = EvaluationDataset()
        test_cases = []

        for item in eval_data:
            prompt = item["input"]
            # Replace placeholders
            prompt = prompt.replace("{{PROJECT_ID}}", project_id).replace(
                "{{CLUSTER_NAME}}", cluster_name
            )

            print(f"Executing agent for prompt: {prompt}")
            actual_output = ""
            if agent_type in ["cli", "binary"]:
                actual_output = run_cli_agent(agent_target, prompt, {})
            elif agent_type == "api":
                actual_output = run_api_agent(agent_target, prompt)
            elif agent_type == "mcp":
                actual_output = run_mcp_agent(agent_target, prompt)

            print(f"--- Agent Response ---\n{actual_output}\n----------------------")

            test_cases.append(
                LLMTestCase(
                    input=prompt,
                    actual_output=actual_output,
                    expected_output=item.get("expected_output", "").replace(
                        "{{PROJECT_ID}}", project_id
                    ),
                    retrieval_context=item.get("retrieval_context", []),
                )
            )
        dataset.test_cases = test_cases

        from deepeval import evaluate

        metrics = create_evaluation_metrics(gemini_model)
        evaluate(dataset.test_cases, metrics=metrics)

    else:
        # Single task flow (Go integration)
        goal = eval_data["goal"]
        context = eval_data["context"]

        # Replace placeholders in goal if any
        goal = goal.replace("{{PROJECT_ID}}", project_id).replace(
            "{{CLUSTER_NAME}}", cluster_name
        )

        # Run the appropriate agent
        actual_output = ""
        if agent_type in ["cli", "binary"]:
            actual_output = run_cli_agent(agent_target, goal, context)
        elif agent_type == "api":
            actual_output = run_api_agent(agent_target, goal)
        elif agent_type == "mcp":
            actual_output = run_mcp_agent(agent_target, goal)

        print(f"--- Agent Response ---\n{actual_output}\n----------------------")

        # DeepEval Scoring
        test_case = LLMTestCase(input=goal, actual_output=actual_output)
        metrics = create_evaluation_metrics(gemini_model)
        outcome_validity, tool_invocation = metrics

        outcome_validity.measure(test_case)
        tool_invocation.measure(test_case)

        result = {
            "OutcomeValidityScore": outcome_validity.score,
            "ToolInvocationScore": tool_invocation.score,
            "Passed": outcome_validity.score >= 0.7 and tool_invocation.score >= 0.8,
            "Reason": f"Goal: {outcome_validity.reason}. Tool: {tool_invocation.reason}",
        }
        print(json.dumps(result))


if __name__ == "__main__":
    main()
