# DevOps Bench

Devops-bench is a benchmark for assessing the performance of agents on a diverse set of DevOps tasks. While existing benchmarks often focus on isolated code generation or simple API calls, `Devops-bench` evaluates AI agents on their ability to perform  (devops) tasks for developers / platform engineers that require critical reasoning and state observation.

The goal is to measure and compare the capability of different agents in completing DevOps workflows. We aim to quantify the value of providing agents with rich environment context, specific operational rules, and specialized tools.


## Live Benchmark Results

See [live leaderboard](https://gke-labs.github.io/devops-bench/) for the latest benchmark results. The data evaluates the following two distinct agent configurations (more to come later) to measure the value-add of domain-specific enhancements.

**Antigravity Agent**
operates using the default configurations and prompts without advanced cloud-specific auxiliary intelligence or specialized guardrails. It serves as the baseline for performance, focusing on the agent's ability to execute raw Kubernetes tasks.

**Antigravity Agent with GCA and GKE special skills and tools**
is an augmented agent integrating layers of optimization to improve reliability and architectural soundness:

* **[GCA (Gemini Cloud Assist)](https://github.com/GoogleCloudPlatform/gemini-cloud-assist-mcp/tree/main)**: Leverages specialized cloud knowledge tools.
* **Rules & Custom Instructions**: Instructions that help the agent to adhere to best practices.

## Task Selection

While our initial results are centered on the scale and sophistication of **Google Kubernetes Engine (GKE)**, this benchmark is designed for the entire cloud-native ecosystem. Whether you are operating on-premises, across hybrid clouds, or on various managed offerings, the fundamental challenges of agentic operations remain the same:

* **Intent to Infrastructure**: Can an agent translate a high-level requirement into a secure, scalable deployment? In fact, the benchmark now supports **Just-In-Time (JIT) Infrastructure provisioning** using OpenTofu to test agents in dynamic environments.

* **Autonomous Operations**: How effectively can an agent maintain the "desired state" in an unpredictable environment?

* **Proactive Troubleshooting**: Can an agent move from detecting a pod failure to diagnosing the root cause and executing a fix?

The benchmark currently consists of 5 tasks simulating realistic deployment scenarios, which we plan to expand further.  You can learn more about the tasks [here](https://github.com/gke-labs/devops-bench/tree/main/tasks).

## Evaluation Metrics
We evaluate the 2 agentic setups on the following key metrics, moving beyond simple pass/fail criteria to understand how the agent achieved the result:

### Outcome Validity
* **Intent-Based Outcome Achievement**: Evaluates if the agent actually performed the action (e.g., deployed resource) rather than just providing instructions, if deployment was requested.

* **Semantic Integrity**: Compares results against the Golden responses to ensure architectural intent is met.

* **Critical Facts**: Verifies if the response fulfills all critical facts and requirements.

* **Scoring**: Measured on a 1-5 scale.

### Tool Invocation
* **Tool Correctness**: Checks if appropriate tools were used and no tool names/parameters were hallucinated.

* **Execution Efficiency**: Checks if the sequence of tool calls was logical and efficient, avoiding loops.

* **Plan Follow-through**: Checks if actions matched stated reasoning.
Scoring: Measured on a 1-5 scale.

### Latency
The total time taken by the agent to complete the task or reach a stopping point.

### Token Usage
The total number of input and output tokens consumed by the agent, measuring the cost-efficiency of the agent.

## Evaluation criteria
The benchmark transitions from simple action validation to a comprehensive assessment of outcome validity and tooling efficiency.

The benchmark utilizes an *LLM-as-a-Judge* mechanism to verify intent and architectural soundness. This judge ingests the agent's full execution trace—including search queries, tool calls, and other events—and maps them against a technical rubric to produce a deterministic score.

### Outcome Validity Skill Rubric
This skill verifies that the final state of the infrastructure matches the user's intent, fulfills the architectural requirements while ignoring non-functional differences.
* Score 5: Outcome fully achieved. Confirms successful application. All critical facts met.
* Score 4: Outcome achieved with minor deviations.
* Score 3: Met manifest intent, but provided instructions instead of executing or missed several critical facts.
* Score 1: No outcome reached, or ignored deployment request / critical facts.

### Tooling Efficiency & Path Validity
This metric assesses the agent's execution path, ensuring it doesn't get stuck in failure loops or use excessive retries.
* Score 5: Perfect tool selection, efficient execution, logical flow. No redundant calls.
* Score 4: Correct tools used, minor inefficiencies.
* Score 3: Succeeded but took convoluted path or minor hallucination recovered from.
* Score 2: Major inefficiencies, loops, or multiple failed calls.
* Score 1: Complete failure, stuck in loop, misunderstood tools.

You can look at the actual rubrics [here](https://github.com/gke-labs/devops-bench/tree/main/skills).

## Running Benchmarks locally
Evaluations can be performed by running the benchmark tasks against your agent and manually or programmatically applying the LLM-as-a-judge method using the Skill based rubrics provided in this repository.

### Step 1: Set up the agent
You can configure the agent in two ways depending on the capabilities you want to test:
* **Option 1**: Using only the core Antigravity agent
This configuration uses the core agent capabilities without external cloud assistance.
* **Option 2**: Antigravity + Gemini Cloud Assist via the Model Context Protocol (MCP) with agent rules.
This [configuration](https://github.com/GoogleCloudPlatform/gemini-cloud-assist-mcp/tree/main) connects your agent to Gemini Cloud Assist for broader cloud management capabilities.

### Step 2: Run tasks with your agent
Feed each task to your configured agent and capture the agent's final response for each task, and ideally a trace of the execution steps (tools called, reasoning steps).

**Note on Infrastructure**: The benchmark now supports automated infrastructure setup via OpenTofu. If a task includes an `infrastructure` block, the evaluator will automatically provision the required environment before running the agent.

### Step 3: Evaluate Responses with LLM-as-a-Judge
To evaluate the results, use a capable LLM to score the agent's responses against the specific criteria defined in the repository's [skills](https://github.com/gke-labs/devops-bench/tree/main/skills) directory.

* **Choose a Judge Model**: Select a powerful LLM to act as your judge (e.g., gemini-3.1-pro-preview or similar).
**Note**: The results in this repository use gemini-3.1-pro-preview for outcome evaluation.

* **Construct the Judge Prompt**: For each of the 5 tasks, construct a prompt (using the SKILL template) for the judge LLM. The prompt should include:
    * The original User Prompt/Task.
    * The Agent's Response (and execution trace if evaluating tool usage).
    * The relevant Skill Rubric (copy the content from the appropriate SKILL.md file).
* **Query the Judge**: Send the prompt to the judge LLM.
* **Extract Scores**: Parse the judge's output to collect the numerical score and the justification.

## Local Container Development

### Building the Image Locally

The image builds with Docker or Podman interchangeably:

- **`Dockerfile`** — the full eval-harness image; installs the packaged `devops-bench` console script and runs the end-to-end pipeline (`devops_bench.run` / `devops_bench.cli`) on Python 3.12.

(`Dockerfile.old` is the retired previous image, kept for reference.)

```bash
docker build -t devops-bench-harness:latest .
```

#### Architecture / Podman on Apple silicon

The `Dockerfile` takes an `ARCH` build arg that selects the OpenTofu archive. It
defaults to the build host's native architecture (`dpkg --print-architecture`),
so a plain build produces a `tofu` binary that matches the image and runs without
emulation — including on an arm64 `podman machine`. Override it only when building
for a different architecture, and keep it consistent with `--platform`:

```bash
# Native build (Podman, Apple silicon): tofu is selected as arm64 automatically
podman build -t devops-bench-harness:latest .

# Explicit arch (e.g. cross-building or pinning)
podman build --build-arg ARCH=arm64 -t devops-bench-harness:latest .
```

> Note: building for `--platform=linux/amd64` on an Apple-silicon `podman machine`
> lets the image build, but the emulated amd64 `tofu` can crash under the VM's x86
> emulation. Building natively (the default `ARCH`) avoids this.

#### Running the harness image

The harness image forwards any arguments to the `devops-bench` CLI, so the task
source and flags go straight after the image name:

```bash
podman run --rm \
  -v "$(pwd)/results:/app/results" \
  -e JUDGE_PROVIDER="google" \
  -e JUDGE_MODEL="gemini-3.1-pro-preview" \
  -e JUDGE_API_KEY="<YOUR_GEMINI_API_KEY>" \
  devops-bench-harness:latest tasks/gcp/create-deployment/task.yaml --no-infra
```

You can also drive it purely via env vars by setting `BENCH_SOURCE` (or the
legacy `BENCH_TASK_FILE`) and passing no positional argument.

### Running the Evaluation

You can run the benchmark in two primary modes: **API Mode** (internal Python loop) or **CLI Mode** (e.g. external Gemini CLI binary).

#### Running via the library/CLI entrypoint

The package installs a `devops-bench` console script that wraps the pipeline. It
reads the same `PROJECT_ID` / `CLUSTER_NAME` / `BENCH_*` / `JUDGE_*` env vars and
lets flags override them:

```bash
devops-bench tasks/create-deployment/task.yaml --project $PROJECT --cluster $CLUSTER
python -m devops_bench tasks/create-deployment/task.yaml --no-infra
```

The same pipeline is callable as a library; `BenchmarkResult.results_path` points
at the run's `results.json`:

```python
from devops_bench.run import run_benchmark, BenchmarkConfig
result = run_benchmark(BenchmarkConfig.from_env("tasks/create-deployment/task.yaml"))
print(result.results_path)
```

#### Option 1: Running in API Mode
This mode uses the internal Python runner.

```bash
docker run -it \
  -v ~/.config/gcloud:/root/.config/gcloud \
  -v $(pwd)/results:/app/results \
  -e CLOUD_PROVIDER="gcp" \
  -e GCP_PROJECT_ID="<YOUR_PROJECT_ID>" \
  -e GKE_CLUSTER_NAME="<YOUR_CLUSTER_NAME>" \
  -e BENCH_TASK_FILE="tasks/create-deployment/task.yaml" \
  -e BENCH_AGENT_TYPE="api" \
  -e BENCH_USE_MCP="true" \
  -e AGENT_PROVIDER="google" \
  -e AGENT_MODEL="gemini-3.1-pro-preview" \
  -e AGENT_API_KEY="<YOUR_GEMINI_API_KEY>" \
  -e JUDGE_PROVIDER="google" \
  -e JUDGE_MODEL="gemini-3.1-pro-preview" \
  -e JUDGE_API_KEY="<YOUR_GEMINI_API_KEY>" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/root/.config/gcloud/application_default_credentials.json \
  devops-bench:latest
```

#### Option 2: Running in CLI Mode
This mode executes the CLI binaries installed inside the container (e.g. gemini
CLI).

```bash
docker run -it \
  -v ~/.config/gcloud:/root/.config/gcloud \
  -v $(pwd)/results:/app/results \
  -e CLOUD_PROVIDER="gcp" \
  -e GCP_PROJECT_ID="<YOUR_PROJECT_ID>" \
  -e GKE_CLUSTER_NAME="<YOUR_CLUSTER_NAME>" \
  -e BENCH_TASK_FILE="tasks/create-deployment/task.yaml" \
  -e BENCH_AGENT_TYPE="cli" \
  -e AGENT_TARGET="gemini" \
  -e AGENT_API_KEY="<YOUR_GEMINI_API_KEY>" \
  -e AGENT_MODEL="gemini-3.1-pro-preview" \
  -e JUDGE_PROVIDER="google" \
  -e JUDGE_MODEL="gemini-3.1-pro-preview" \
  -e JUDGE_API_KEY="<YOUR_GEMINI_API_KEY>" \
  devops-bench:latest
```

#### Flag Descriptions

| Flag | Description |
| :--- | :--- |
| `-it` | Runs the container in interactive mode with a TTY, allowing you to see real-time output. |
| `-v ~/.config/gcloud:/root/.config/gcloud` | Mounts your local Google Cloud configuration into the container so it can use your existing credentials. |
| `-e GOOGLE_APPLICATION_CREDENTIALS` | Path to the credentials file (required for OpenTofu and some agent tools). |
| `-v $(pwd)/results:/app/results` | Mounts the local `results` directory to the container. This ensures that evaluation outputs generated inside the container are saved to your host machine. |
| **Infrastructure** | |
| `-e CLOUD_PROVIDER` | Specifies the cloud provider (e.g., `gcp`). |
| `-e GCP_PROJECT_ID` | The ID of the Google Cloud Project to run evaluations against. |
| `-e GKE_CLUSTER_NAME` | The name of the GKE cluster used for the evaluation. If JIT infra is used, this may be overwritten by the JIT-created cluster name. |
| **Benchmark Control** | |
| `-e BENCH_TASK_FILE` | Path to the specific YAML task file you want to evaluate. |
| `-e BENCH_AGENT_TYPE` | The type of agent to run (`api` or `cli`). |
| `-e BENCH_USE_MCP` | Boolean flag (`true`/`false`) to enable or disable the Model Context Protocol (MCP) server. |
| **Agent Configuration** | |
| `-e AGENT_TARGET` | Path to the agent binary (required for `cli` mode, e.g., `gemini`). |
| `-e AGENT_PROVIDER` | The LLM provider for the agent (e.g., `google` or `anthropic`). |
| `-e AGENT_MODEL` | The specific model version to use for the agent (e.g., `gemini-3.1-pro-preview`). |
| `-e AGENT_API_KEY` | Your API key for the agent's LLM provider. |
| **Judge Configuration** | |
| `-e JUDGE_PROVIDER` | The LLM provider for the judge (e.g., `google`). |
| `-e JUDGE_MODEL` | The specific model version to use for evaluation (e.g., `gemini-3.1-pro-preview`). |
| `-e JUDGE_API_KEY` | Your API key for the judge's LLM provider. |
| | |
| `devops-bench:latest` | The name and tag of the image to run. |

## DeepEval Integration

DevOps Bench uses **DeepEval** for evaluating agent performance. DeepEval is an open-source LLM evaluation framework.

We use **GEval** (LLM-as-a-judge) metrics to score the agent's output against specific criteria.

### Metrics Collected

- **OutcomeValidity**: Evaluates whether the agent's final output fulfills the requirements specified in the task. It checks for semantic and architectural correctness.
- **ToolInvocation**: Evaluates whether the agent used tools correctly and effectively to accomplish the task. It inspects the `tools_used` and `execution_trace` in the actual output.
- **Dynamic Checklist Checks**: For each requirement listed in the `expected_output` of a task, a dynamic GEval metric is created to verify if that specific requirement was met.
- **Latency**: The total time taken by the agent to execute the task is recorded.
- **Token Usage**: Input, output, and total token counts are captured (when available from the agent runner) to measure cost and efficiency.

### Configuration

To run evaluations, you must provide a `JUDGE_API_KEY` as DeepEval uses an LLM to grade the outputs.

You can specify the model used for evaluation via the `JUDGE_MODEL` environment variable.

## Viewing Results

The results of the evaluation are saved in the `results/` directory on your host machine (thanks to the volume mount `-v $(pwd)/results:/app/results`).

Each run creates a new subdirectory with a timestamp (e.g., `run_YYYYMMDD_HHMMSS`), containing:
- `results.json`: The detailed execution results, including inputs, outputs, latency, and evaluation scores.
- `generated_files/`: A directory containing any files generated by the agent during the task.

You can inspect `results.json` to see the pass rate and detailed feedback for each check.

