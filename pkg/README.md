# GKE Agent Evaluation Suite

This directory contains evaluation suite logic for the GKE Agent, using DeepEval.

## Prerequisites

- **Python 3.10 or newer** (Required by DeepEval dependencies).
- Load dependencies (run from project root):
  ```bash
  source .venv/bin/activate
  python3 -m pip install -r requirements.txt
  ```
- Set up your **API Key**:
  ```bash
  export AGENT_API_KEY="your-api-key"
  export JUDGE_API_KEY="your-api-key" # Can be the same as above
  ```

## How to Run Evaluations

> [!IMPORTANT]
> All commands below should be run from the **project root** directory.

### 1. Running the Dataset Evaluation (Python)

To run evaluation on tasks definitions dynamically located in the tasks directory:

```bash
source .venv/bin/activate
export BENCH_AGENT_TYPE="api" # Options: 'cli', 'api', 'binary'
export AGENT_MODEL="gemini-3.1-pro-preview" # Use for 'api' mode
export AGENT_TARGET="gemini" # Use for 'cli' mode (path to binary)
export GCP_PROJECT_ID="your-gcp-project"
export GKE_CLUSTER_NAME="your-cluster-name"

python3 pkg/evaluator/evaluate.py tasks/
```


#### Running the LLM Agent mode with MCP
The MCP-enabled API agent runner supports multiple LLM providers and optional MCP tool usage. You can set the following configurations:

```bash
# Choose provider: 'google' or 'anthropic'
export AGENT_PROVIDER="google" 
# Toggle MCP tools: 'true' or 'false'
export BENCH_USE_MCP="true" 
# For Vertex AI support (recommended)
export GCP_PROJECT_ID="your-gcp-project"
export GCP_VERTEX_LOCATION="us-central1"
# If using specific models
export AGENT_MODEL="gemini-3.1-pro-preview"
# Path to MCP server binary (if BENCH_USE_MCP=true)
export MCP_SERVER_PATH="third_party/gke-mcp/gke-mcp"
```

### 2. Running via Pytest

If you prefer to run the tests via Pytest (uses `pkg/evaluator/test_gke_agent.py`):

```bash
source .venv/bin/activate
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 -m pytest pkg/evaluator/test_gke_agent.py
```

## Metrics Used

- **OutcomeValidity**: Evaluates if the agent achieved the goal based on the rubric.
- **ToolInvocation**: Verifies if the agent used relevant tools.

