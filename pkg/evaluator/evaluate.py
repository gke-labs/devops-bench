import asyncio
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
import argparse
from deepeval import assert_test, evaluate
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams
from deepeval.tracing import observe
from deepeval.models import DeepEvalBaseLLM
from deepeval.dataset import EvaluationDataset
from google import genai
from anthropic import AnthropicVertex, Anthropic

# Ensure module imports resolve locally
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../pkg/agents/runner/api")
    ),
)

from pkg.agents.runner.api.llm_adapters import (
    AnthropicClientAdapter,
    GeminiClientAdapter,
    OllamaClientAdapter,
)

from pkg.agents.runner.api.api import run_api_agent
from pkg.agents.runner.gcli import run_cli_agent
from pkg.runenv import RunEnv, parallel_enabled
from pkg.evaluator.loader import (
    load_from_tasks_dir,
    safe_parse_yaml,
    parse_documentation_from_yaml,
)
import threading
from pkg.manager.manager import ScenarioManager, pick_free_port
from deployers.factory import get_deployer


SYSTEM_INSTRUCTION = """You are an expert DevOps engineer. When asked to make an app production-ready or perform operational tasks like secret rotation, you MUST apply the changes directly to the GKE cluster and GCP APIs using your tools. Do NOT output bash scripts, templates, or instructions for the user to run manually. You must complete the entire operation yourself using tool calls."""

SYSTEM_INSTRUCTION_NO_MCP = """You are an expert DevOps engineer. Respond with complete, production-ready Kubernetes manifests and configurations that satisfy the request. Output the full YAML or relevant artifacts directly in your response."""


def validate_config(role, provider, model):
    """Logs the detected configuration. TODO: Add consistency checks."""
    print(f"DEBUG: Validating {role} config - Provider: {provider}, Model: {model}")
    # TODO: Add consistency checks (e.g., google provider expects gemini-* models)
    pass


class GeminiDeepEvalModel(DeepEvalBaseLLM):
    """Wrapper for Gemini SDK to be used with DeepEval."""

    def __init__(self, model_name=None):
        if not model_name:
            model_name = os.environ.get("JUDGE_MODEL", "gemini-3.1-pro-preview")

        self.model_name = model_name
        project_id = os.environ.get("PROJECT_ID") or os.environ.get("GCP_PROJECT_ID")
        location = os.environ.get("LOCATION") or os.environ.get("GCP_VERTEX_LOCATION", "us-central1")
        api_key = os.environ.get("JUDGE_API_KEY")

        validate_config(
            "judge", os.environ.get("JUDGE_PROVIDER", "google"), self.model_name
        )

        if api_key:
            self.client = genai.Client(api_key=api_key)
        elif project_id:
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


class AnthropicDeepEvalModel(DeepEvalBaseLLM):
    """Wrapper for Anthropic SDK to be used with DeepEval."""

    def __init__(self, model_name=None):
        if not model_name:
            model_name = os.environ.get("JUDGE_MODEL", "claude-opus-4-6")

        self.model_name = model_name
        project_id = os.environ.get("PROJECT_ID") or os.environ.get("GCP_PROJECT_ID")
        location = os.environ.get("LOCATION") or os.environ.get("GCP_VERTEX_LOCATION", "us-central1")
        api_key = os.environ.get("JUDGE_API_KEY")

        validate_config(
            "judge", os.environ.get("JUDGE_PROVIDER", "anthropic"), self.model_name
        )

        if api_key:
            self.client = Anthropic(api_key=api_key)
        elif project_id:
            self.client = AnthropicVertex(region=location, project_id=project_id)
        else:
            self.client = Anthropic()

    def load_model(self):
        return self.client

    def generate(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model_name,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        if hasattr(response, "content"):
            for content in response.content:
                if hasattr(content, "type") and content.type == "text":
                    text += content.text
        return text

    async def a_generate(self, prompt: str) -> str:
        return self.generate(prompt)

    def get_model_name(self):
        return self.model_name


class OllamaDeepEvalModel(DeepEvalBaseLLM):
    """Wrapper for Ollama (OpenAI-compatible API) to be used with DeepEval."""

    def __init__(self, model_name=None):
        from openai import OpenAI
        if not model_name:
            model_name = os.environ.get("JUDGE_MODEL", "gemma4:2b")
        self.model_name = model_name
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.client = OpenAI(base_url=base_url, api_key="ollama")
        validate_config("judge", "ollama", self.model_name)

    def load_model(self):
        return self.client

    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""

    async def a_generate(self, prompt: str) -> str:
        return self.generate(prompt)

    def get_model_name(self):
        return self.model_name


def replace_placeholders(text, project_id, cluster_name):
    """Replaces placeholders in the text.

    Note: TARGET_DEPLOYMENT_NAME and NAMESPACE act as the integration contract
    fed dynamically by the upstream Infra Provisioning layer after cluster bring-up.
    """
    app_location = os.environ.get("APP_LOCATION", "")
    target_deployment = os.environ.get("TARGET_DEPLOYMENT_NAME", "hello-app")
    namespace = os.environ.get("NAMESPACE", "production")
    return (
        text.replace("{{PROJECT_ID}}", project_id)
        .replace("{{GCP_PROJECT_ID}}", project_id)
        .replace("{{CLUSTER_NAME}}", cluster_name)
        .replace("{{GKE_CLUSTER_NAME}}", cluster_name)
        .replace("{{APP_LOCATION}}", app_location)
        .replace("{{TARGET_DEPLOYMENT_NAME}}", target_deployment)
        .replace("{{NAMESPACE}}", namespace)
    )


def print_configuration_context(
    cloud_provider,
    project_id,
    cluster_name,
    bench_agent_type,
    agent_target,
    bench_use_mcp,
    mcp_server_path,
    app_location,
    agent_provider,
    agent_model,
    judge_provider,
    judge_model,
):
    """Prints a formatted summary of the active evaluation configurations."""
    print("-" * 50)
    print("Configuration Context:")
    print(f"  - CLOUD_PROVIDER:       {cloud_provider}")
    print(f"  - PROJECT_ID:           {project_id}")
    print(f"  - CLUSTER_NAME:         {cluster_name}")
    print(f"  - BENCH_AGENT_TYPE:     {bench_agent_type}")
    print(f"  - AGENT_TARGET:         {agent_target}")
    print(f"  - BENCH_USE_MCP:        {bench_use_mcp}")
    print(f"  - MCP_SERVER_PATH:      {mcp_server_path}")
    print(f"  - APP_LOCATION:         {app_location}")
    print(f"  - AGENT_PROVIDER:       {agent_provider}")
    print(f"  - AGENT_MODEL:          {agent_model}")
    print(f"  - JUDGE_PROVIDER:       {judge_provider}")
    print(f"  - JUDGE_MODEL:          {judge_model}")
    print("-" * 50)


def load_evaluation_data(input_path):
    """Loads task specifications from a folder, a YAML file, or a JSON file."""
    if os.path.isdir(input_path):
        print(f"Loading tasks specifications dynamically from {input_path} folder...")
        eval_data = load_from_tasks_dir(input_path)
    elif input_path.endswith((".yaml", ".yml")):
        print(f"Loading task specification from {input_path}...")
        with open(input_path, "r") as f:
            yaml_text = f.read()
            content = safe_parse_yaml(yaml_text)
            docs = parse_documentation_from_yaml(yaml_text)
            eval_data = [
                {
                    "task_id": content.get("task_id", 1),
                    "name": content.get("name", "Legacy Case"),
                    "input": content.get("prompt", "").strip(),
                    "expected_output": content.get("expected_output", "").strip(),
                    "retrieval_context": content.get("retrieval_context", []),
                    "chaos_spec": content.get("chaos_spec"),
                    "verification_spec": content.get("verification_spec"),
                    "infrastructure": content.get("infrastructure", {}),
                    "documentation": docs,
                }
            ]
    else:
        with open(input_path, "r") as f:
            eval_data = json.load(f)

    if isinstance(eval_data, dict):
        eval_data = [
            {
                "task_id": eval_data.get("task_id", 1),
                "name": eval_data.get("name", "Legacy Case"),
                "input": eval_data.get("goal", eval_data.get("input", "")),
                "expected_output": eval_data.get("expected_output", ""),
                "retrieval_context": eval_data.get("retrieval_context", []),
                "chaos_spec": eval_data.get("chaos_spec"),
                "verification_spec": eval_data.get("verification_spec"),
                "infrastructure": eval_data.get("infrastructure", {}),
            }
        ]
    elif isinstance(eval_data, list):
        for item in eval_data:
            if "input" not in item and "goal" in item:
                item["input"] = item["goal"]
    return eval_data


def load_configuration_context():
    """Retrieves, validates, and logs the active benchmark and agent configurations."""
    bench_agent_type = os.environ.get("BENCH_AGENT_TYPE", "cli").lower()
    agent_target = os.environ.get("AGENT_TARGET", "./my-agent")

    judge_provider = os.environ.get("JUDGE_PROVIDER", "google")
    judge_model_name = os.environ.get("JUDGE_MODEL")

    if judge_provider == "google":
        if not judge_model_name:
            judge_model_name = "gemini-3.1-pro-preview"
        judge_model = GeminiDeepEvalModel(model_name=judge_model_name)
    elif judge_provider == "anthropic":
        if not judge_model_name:
            judge_model_name = "claude-opus-4-6"
        judge_model = AnthropicDeepEvalModel(model_name=judge_model_name)
    elif judge_provider == "ollama":
        if not judge_model_name:
            judge_model_name = "gemma4:2b"
        judge_model = OllamaDeepEvalModel(model_name=judge_model_name)
    else:
        print(
            f"Warning: Unknown judge provider '{judge_provider}'. Defaulting to Gemini."
        )
        judge_model_name = judge_model_name or "gemini-3.1-pro-preview"
        judge_model = GeminiDeepEvalModel(model_name=judge_model_name)

    project_id = os.environ.get("PROJECT_ID") or os.environ.get("GCP_PROJECT_ID")
    cluster_name = os.environ.get("CLUSTER_NAME") or os.environ.get("GKE_CLUSTER_NAME")

    if not project_id or not cluster_name:
        print("Error: PROJECT_ID (or GCP_PROJECT_ID) and CLUSTER_NAME (or GKE_CLUSTER_NAME) must be set.")
        sys.exit(1)

    # Establish per-run isolation BEFORE any provisioning so every gcloud /
    # kubectl / tofu / agent subprocess inherits the run-scoped kubeconfig,
    # gcloud config, and tofu data dir. A no-op unless BENCH_PARALLEL is set.
    run_env = RunEnv.create(parallel=parallel_enabled())
    run_env.apply()
    cluster_name = run_env.cluster_name(cluster_name)

    bench_use_mcp = os.environ.get("BENCH_USE_MCP", "true")
    mcp_server_path = os.environ.get("MCP_SERVER_PATH", "third_party/gke-mcp/gke-mcp")
    app_location = os.environ.get("APP_LOCATION", "N/A")
    agent_provider = os.environ.get("AGENT_PROVIDER", "google")
    agent_model = os.environ.get("AGENT_MODEL", "gemini-3.1-pro-preview")
    cloud_provider = os.environ.get("CLOUD_PROVIDER", "gcp")

    print_configuration_context(
        cloud_provider,
        project_id,
        cluster_name,
        bench_agent_type,
        agent_target,
        bench_use_mcp,
        mcp_server_path,
        app_location,
        agent_provider,
        agent_model,
        judge_provider,
        judge_model_name,
    )

    return bench_agent_type, agent_target, judge_model, project_id, cluster_name


def execute_agent(bench_agent_type, agent_target, prompt, context):
    """Executes the appropriate agent and returns standardized results."""
    if bench_agent_type in ["cli", "binary"]:
        bench_use_mcp_env = os.environ.get("BENCH_USE_MCP", "true").lower()
        bench_use_mcp = bench_use_mcp_env == "true"
        return run_cli_agent(
            agent_target,
            prompt,
            context,
            bench_use_mcp=bench_use_mcp,
            system_instruction=SYSTEM_INSTRUCTION,
        )
    elif bench_agent_type == "api":
        mcp_server_path = os.environ.get(
            "MCP_SERVER_PATH", "third_party/gke-mcp/gke-mcp"
        )
        provider = os.environ.get("AGENT_PROVIDER", "google")
        if provider == "gemini" or provider == "google":
            llm_client = GeminiClientAdapter()
        elif provider == "anthropic":
            llm_client = AnthropicClientAdapter()
        elif provider == "ollama":
            llm_client = OllamaClientAdapter()
        else:
            raise ValueError(f"Unknown provider: {provider}")
        bench_use_mcp_env = os.environ.get("BENCH_USE_MCP", "true").lower()
        bench_use_mcp = bench_use_mcp_env == "true"
        sys_instruction = SYSTEM_INSTRUCTION if bench_use_mcp else SYSTEM_INSTRUCTION_NO_MCP
        return asyncio.run(
            run_api_agent(
                prompt,
                mcp_server_path,
                llm_client,
                bench_use_mcp=bench_use_mcp,
                system_instruction=sys_instruction,
            )
        )
    else:
        raise ValueError(f"Unknown agent type: {bench_agent_type}")


def create_evaluation_metrics(model):
    with open("skills/outcome-validity-checklist.md", "r") as f:
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


def evaluate_documentation_grounding(documentation, all_test_case, judge_model, scores):
    """Evaluates documentation constraints via GEval and calculates GroundingAccuracy."""
    doc_metrics = []
    doc_constraints_map = {}
    for doc in documentation:
        for constraint in doc.get("constraints", []):
            c_text = constraint["text"]
            c_crit = constraint["critical"]
            doc_constraints_map[c_text] = c_crit
            doc_metrics.append(
                GEval(
                    name=f"Doc Constraint: {c_text}",
                    criteria=(
                        "Verify that the actual output fulfills this specific"
                        f" documentation constraint/requirement: {c_text}"
                    ),
                    evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT],
                    model=judge_model,
                )
            )

    if not doc_metrics:
        return

    print(
        f"Evaluating {len(doc_metrics)} documentation constraint metrics sequentially..."
    )
    for m in doc_metrics:
        try:
            print(f"Evaluating doc metric: {m.name}...")
            result = evaluate([all_test_case], metrics=[m])
            for test_result in result.test_results:
                for metric_data in test_result.metrics_data:
                    m_name = metric_data.name
                    if m_name.endswith(" [GEval]"):
                        m_name = m_name[:-8]
                    scores[m_name] = {
                        "score": metric_data.score,
                        "success": metric_data.success,
                        "reason": getattr(metric_data, "reason", None),
                    }
        except Exception as e:
            print(f"Error evaluating doc metric {m.name}: {e}")

    total_constraints = len(doc_metrics)
    applied_constraints = 0
    critical_total = sum(1 for crit in doc_constraints_map.values() if crit)
    critical_applied = 0

    for c_text, c_crit in doc_constraints_map.items():
        m_name = f"Doc Constraint: {c_text}"
        if m_name in scores and scores[m_name]["success"]:
            applied_constraints += 1
            if c_crit:
                critical_applied += 1

    # Score 5.0 (Success), 2.5 (Partial), 0.0 (Failure)
    if total_constraints == 0:
        grounding_score = 5.0
    elif applied_constraints == total_constraints:
        grounding_score = 5.0
    elif applied_constraints == 0:
        grounding_score = 0.0
    elif critical_applied < critical_total:
        grounding_score = 2.5
    else:
        non_critical_total = total_constraints - critical_total
        non_critical_applied = applied_constraints - critical_applied
        if non_critical_total > 0:
            grounding_score = 2.5 + 2.5 * (non_critical_applied / non_critical_total)
        else:
            grounding_score = 5.0

    recall_accuracy = (
        applied_constraints / total_constraints if total_constraints > 0 else 1.0
    )

    scores["GroundingAccuracy"] = {
        "score": grounding_score,
        "success": grounding_score >= 4.0,
        "reason": f"Applied {applied_constraints} out of {total_constraints} documented constraints (Critical: {critical_applied}/{critical_total}).",
    }
    scores["ParameterRecallAccuracy"] = recall_accuracy


def calculate_doc_retrieval_rate(documentation, trajectory) -> float:
    """Calculates the percentage of mapped documentation guides accessed in trajectory."""
    if not documentation:
        return 0.0

    accessed_docs = set()
    for doc in documentation:
        doc_name_lower = doc["doc_name"].lower()
        url_lower = doc["url"].lower()
        found_in_trajectory = False
        for step in trajectory:
            step_str = json.dumps(step).lower()
            if doc_name_lower in step_str or (url_lower and url_lower in step_str):
                found_in_trajectory = True
                break
        if found_in_trajectory:
            accessed_docs.add(doc["doc_name"])

    return len(accessed_docs) / len(documentation) if len(documentation) > 0 else 0.0


def evaluate_metrics_batch(detailed_results, judge_model):
    """Calculates batch metrics for a list of execution results."""

    print("\nStarting batch post-processing evaluation metrics...")
    for res in detailed_results:
        prompt = res["input"]
        actual_output = res["output"]
        trajectory = res["trajectory"]
        expected_output = res["expected_output"]
        latency = res["latency"]
        name = res["name"]
        retrieval_context = res["retrieval_context"]
        documentation = res.get("documentation", [])

        metrics = create_evaluation_metrics(judge_model)
        outcome_criteria = metrics[0].criteria
        tool_criteria = metrics[1].criteria

        # Extract checklist items ONLY from the critical requirements section to avoid parsing YAML lists
        reqs_section = expected_output
        if "critical requirements:" in reqs_section.lower():
            parts = re.split(r"(?i)critical requirements\s*:", reqs_section, maxsplit=1)
            if len(parts) > 1:
                reqs_section = parts[1]

        if "expected manifest generated:" in reqs_section.lower():
            parts = re.split(
                r"(?i)expected manifest generated\s*:", reqs_section, maxsplit=1
            )
            reqs_section = parts[0]

        bench_use_mcp = os.environ.get("BENCH_USE_MCP", "true").lower() == "true"
        raw_checklist_items = [
            line.strip("- ")
            for line in reqs_section.split("\n")
            if line.strip().startswith("-")
        ]
        checklist_items = []
        for item in raw_checklist_items:
            if not bench_use_mcp and "expected tool call" in item.lower():
                print(f"Skipping Expected Tool Call criteria: '{item}'")
                continue
            checklist_items.append(item)
        dynamic_metrics = []
        for item in checklist_items:
            dynamic_metrics.append(
                GEval(
                    name=f"Check: {item}",
                    criteria=(
                        "Verify that the actual output fulfills this specific"
                        f" requirement: {item}"
                    ),
                    evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT],
                    model=judge_model,
                )
            )

        outcome_validity = GEval(
            name="OutcomeValidity",
            criteria=outcome_criteria,
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
            ],
            model=judge_model,
        )

        tool_invocation = GEval(
            name="ToolInvocation",
            criteria=tool_criteria,
            threshold=0.8,
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
            ],
            model=judge_model,
        )

        outcome_test_case = LLMTestCase(
            input=prompt,
            actual_output=actual_output if actual_output else "No response generated",
            expected_output=expected_output,
            retrieval_context=retrieval_context,
            latency=latency,
        )

        combined_actual = {
            "tools_used": res.get("tools", []),
            "execution_trace": trajectory,
        }
        tool_test_case = LLMTestCase(
            input=prompt,
            actual_output=json.dumps(combined_actual, indent=2),
            expected_output=expected_output,
            latency=latency,
        )

        all_context = {
            "tools_used": res.get("tools", []),
            "execution_trace": trajectory,
            "text_output": actual_output if actual_output else "No response generated",
        }
        all_test_case = LLMTestCase(
            input=prompt,
            actual_output=json.dumps(all_context, indent=2),
            expected_output=expected_output,
            latency=latency,
        )

        print(f"Evaluating metrics for: {name}...")
        outcome_result = evaluate([outcome_test_case], metrics=[outcome_validity])

        scores = {}
        for test_result in outcome_result.test_results:
            for metric_data in test_result.metrics_data:
                scores[metric_data.name] = {
                    "score": metric_data.score,
                    "success": metric_data.success,
                    "reason": getattr(metric_data, "reason", None),
                }

        if os.environ.get("BENCH_USE_MCP", "true").lower() == "true":
            tool_result = evaluate([tool_test_case], metrics=[tool_invocation])
            for test_result in tool_result.test_results:
                for metric_data in test_result.metrics_data:
                    scores[metric_data.name] = {
                        "score": metric_data.score,
                        "success": metric_data.success,
                        "reason": getattr(metric_data, "reason", None),
                    }

        if dynamic_metrics:
            print(f"Evaluating {len(dynamic_metrics)} dynamic metrics sequentially...")
            for m in dynamic_metrics:
                try:
                    print(f"Evaluating metric: {m.name}...")
                    result = evaluate([all_test_case], metrics=[m])
                    for test_result in result.test_results:
                        for metric_data in test_result.metrics_data:
                            name = metric_data.name
                            if name.endswith(" [GEval]"):
                                name = name[:-8]
                            scores[name] = {
                                "score": metric_data.score,
                                "success": metric_data.success,
                                "reason": getattr(metric_data, "reason", None),
                            }
                except Exception as e:
                    print(f"Error evaluating metric {m.name}: {e}")

            passed_checks = sum(
                1
                for m in dynamic_metrics
                if m.name in scores and scores[m.name]["success"]
            )
            total_checks = len(dynamic_metrics)
            scores["ChecklistScore"] = {
                "score": passed_checks / total_checks if total_checks > 0 else 0.0,
                "success": (
                    passed_checks / total_checks >= 0.8 if total_checks > 0 else False
                ),
                "reason": f"Passed {passed_checks} out of {total_checks} checks.",
            }

        # Grounding Accuracy & Recall
        if documentation:
            evaluate_documentation_grounding(
                documentation, all_test_case, judge_model, scores
            )
            scores["DocRetrievalRate"] = calculate_doc_retrieval_rate(
                documentation, trajectory
            )

        if res.get("chaos_spec"):
            print(f"Evaluating Planned Chaos Mode and Performance metrics...")
            chaos_report = res.get("chaos_report", {})
            actual_fault = chaos_report.get("injected_fault", "pod deletion")

            diag_metric = GEval(
                name="DiagnosisAccuracy",
                criteria=f"Did the agent accurately identify that the fault injected was '{actual_fault}'?",
                evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT],
                model=judge_model,
            )

            rec_metric = GEval(
                name="GracefulRecovery",
                criteria="Did the agent follow a graceful recovery process (e.g., maintaining uptime, zero downtime)?",
                evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT],
                model=judge_model,
            )

            try:
                chaos_result = evaluate(
                    [all_test_case], metrics=[diag_metric, rec_metric]
                )
                for test_result in chaos_result.test_results:
                    for metric_data in test_result.metrics_data:
                        metric_name = metric_data.name
                        if metric_name.endswith(" [GEval]"):
                            metric_name = metric_name[:-8]
                        scores[metric_name] = {
                            "score": metric_data.score,
                            "success": metric_data.success,
                            "reason": getattr(metric_data, "reason", None),
                        }
            except Exception as e:
                print(f"Error evaluating chaos metrics: {e}")

            perf_report = res.get("perf_report", {})
            scores["Workload_Deployment_Time_Seconds"] = perf_report.get(
                "deployment_time_seconds"
            )
            scores["Workload_Uptime_Percentage"] = perf_report.get("uptime_percentage")
            scores["Resource_Utilization_Efficiency"] = perf_report.get(
                "resource_utilization_efficiency"
            )

        res["scores"] = scores


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 evaluate.py <tasks_directory>")
        sys.exit(1)

    input_path = sys.argv[1]
    eval_data = load_evaluation_data(input_path)

    limit = os.environ.get("EVAL_LIMIT")
    if limit and isinstance(eval_data, list):
        eval_data = eval_data[: int(limit)]
        print(f"Limiting evaluation to the first {limit} cases.")

    bench_agent_type, agent_target, judge_model, project_id, cluster_name = (
        load_configuration_context()
    )

    print(f"Running dataset evaluation with {len(eval_data)} cases...")
    dataset = EvaluationDataset()
    test_cases = []
    detailed_results = []

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = f"run_{timestamp}"
    # The timestamp has 1-second resolution; append the (process-unique) run id
    # so two evaluator processes started in the same second do not collide on a
    # single results/run_<ts>/ directory.
    run_id = os.environ.get("RUN_ID")
    if run_id:
        run_name = f"{run_name}_{re.sub(r'[^A-Za-z0-9_-]', '-', run_id)}"
    run_dir = f"results/{run_name}"
    os.makedirs(run_dir, exist_ok=True)

    for item in eval_data:
        infra_config = item.get("infrastructure", {})
        deployer = get_deployer(infra_config, project_id, cluster_name)

        try:
            print(f"--- Provisioning Infrastructure for: {item['name']} ---")
            deployer.up()
            cluster_info = deployer.get_cluster_info()

            # Use dynamic cluster name from deployer for prompt replacement
            active_cluster_name = cluster_info.get("name", cluster_name)
            prompt = replace_placeholders(
                item["input"], project_id, active_cluster_name
            )

            target_deployment = os.environ.get(
                "TARGET_DEPLOYMENT_NAME", "hypercomputer-d1-frontend"
            )
            namespace = os.environ.get("NAMESPACE", "default")

            chaos_spec = item.get("chaos_spec")
            verification_spec = item.get("verification_spec")
            scenario_manager = None

            if chaos_spec:
                try:
                    # Replace placeholders in chaos_spec string/dict
                    chaos_spec_processed = replace_placeholders(
                        json.dumps(chaos_spec)
                        if isinstance(chaos_spec, (dict, list))
                        else str(chaos_spec),
                        project_id,
                        active_cluster_name,
                    )
                    spec_list = json.loads(chaos_spec_processed)

                    verification_spec_list = []
                    if verification_spec:
                        verification_spec_processed = replace_placeholders(
                            json.dumps(verification_spec)
                            if isinstance(verification_spec, (dict, list))
                            else str(verification_spec),
                            project_id,
                            active_cluster_name,
                        )
                        verification_spec_list = json.loads(verification_spec_processed)

                    if spec_list:
                        spec = spec_list[0]
                        local_port = pick_free_port() if parallel_enabled() else None
                        scenario_manager = ScenarioManager(
                            target_deployment, namespace, local_port=local_port
                        )
                        t = threading.Thread(
                            target=scenario_manager.run_chaos_and_verification,
                            args=(spec, verification_spec_list),
                        )
                        t.daemon = True
                        t.start()
                except Exception as e:
                    print(f"Warning: Failed to start ScenarioManager: {e}")

            if scenario_manager:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[
                    :-3
                ]
                print(
                    f"[{timestamp}] Waiting for Chaos Agent to establish the cluster load spike...",
                    flush=True,
                )
                scenario_manager.chaos_active_event.wait(timeout=45)
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[
                    :-3
                ]
                print(
                    f"[{timestamp}] Cluster load spike is now active. Proceeding with Operator Agent...",
                    flush=True,
                )

            print(f"Executing agent for prompt: {prompt}")

            before_files = set(os.listdir("."))
            agent_res = execute_agent(bench_agent_type, agent_target, prompt, {})
            after_files = set(os.listdir("."))

            new_files = after_files - before_files
            if new_files:
                gen_files_dir = os.path.join(run_dir, "generated_files")
                os.makedirs(gen_files_dir, exist_ok=True)
                for f in new_files:
                    target_path = os.path.join(gen_files_dir, f)
                    if os.path.isdir(f):
                        shutil.copytree(f, target_path, dirs_exist_ok=True)
                    elif os.path.isfile(f):
                        shutil.copy(f, target_path)

            actual_output = agent_res.get("output", "")
            latency = agent_res.get("latency", 0.0)

            expected_output_raw = item.get("expected_output", "")
            expected_output = replace_placeholders(
                expected_output_raw, project_id, active_cluster_name
            )

            chaos_report = {}
            perf_report = {}
            if scenario_manager:
                print(
                    "[ScenarioManager] Waiting for background metrics collection to complete...",
                    flush=True,
                )
                t.join(timeout=90)
                chaos_report, perf_report = scenario_manager.get_reports()

            detailed_results.append(
                {
                    "input": prompt,
                    "output": actual_output,
                    "latency": latency,
                    "tokens": agent_res.get("tokens", {}),
                    "tools": agent_res.get("tools", {}),
                    "trajectory": agent_res.get("trajectory", []),
                    "skills": agent_res.get("skills", []),
                    "name": item["name"],
                    "expected_output": expected_output,
                    "expected_output_raw": expected_output_raw,
                    "retrieval_context": item.get("retrieval_context", []),
                    "chaos_spec": item.get("chaos_spec"),
                    "chaos_report": chaos_report
                    if scenario_manager
                    else agent_res.get("chaos_report", {}),
                    "perf_report": perf_report
                    if scenario_manager
                    else agent_res.get("perf_report", {}),
                    "documentation": item.get("documentation", []),
                }
            )

            print(f"--- Agent Response ---\n{actual_output}\n----------------------")

        except Exception as e:
            print(f"Critical error during task {item['name']}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            global_no_teardown = os.environ.get("BENCH_NO_TEARDOWN", "false").lower() == "true"
            if infra_config.get("teardown", True) and not global_no_teardown:
                print(f"--- Tearing Down Infrastructure for: {item['name']} ---")
                try:
                    deployer.down()
                except Exception as teardown_err:
                    print(f"Teardown failed (potential resource leak): {teardown_err}")

        if detailed_results:
            expected_output_raw = item.get("expected_output", "")
            detailed_results[-1]["expected_output"] = replace_placeholders(
                expected_output_raw, project_id, cluster_name
            )
            detailed_results[-1]["name"] = item["name"]
            detailed_results[-1]["retrieval_context"] = item.get("retrieval_context", [])
            detailed_results[-1]["chaos_spec"] = item.get("chaos_spec")
            detailed_results[-1]["verification_spec"] = item.get("verification_spec")

            chaos_report = {}
            perf_report = {}
            if scenario_manager:
                print(
                    "[ScenarioManager] Waiting for background metrics collection to complete...",
                    flush=True,
                )
                t.join(timeout=90)
                chaos_report, perf_report = scenario_manager.get_reports()

            detailed_results[-1]["chaos_report"] = chaos_report
            detailed_results[-1]["perf_report"] = perf_report
            detailed_results[-1]["documentation"] = item.get("documentation", [])

    # Save tasks execution outputs immediately
    with open(os.path.join(run_dir, "results.json"), "w") as f:
        json.dump(detailed_results, f, indent=2)
    print(f"Execution complete. Results safely saved to {run_dir}/results.json")

    # 2. Loop to EVALUATE metrics for all tasks at the end
    # 2. Execute batch metrics post-processing turn via helper function
    evaluate_metrics_batch(detailed_results, judge_model)

    with open(os.path.join(run_dir, "results.json"), "w") as f:
        json.dump(detailed_results, f, indent=2)
    print(
        f"Post-processing evaluation complete. Updated results saved to {run_dir}/results.json"
    )

    print("\n=== Detailed Results ===")
    print(json.dumps(detailed_results, indent=2))
    print("=========================")


if __name__ == "__main__":
    main()
