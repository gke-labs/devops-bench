# GKE Agent Evaluation Suite

This directory contains the Go wrapper and Python evaluation suite for the GKE Agent, using DeepEval.

## Prerequisites

- **Python 3.10 or newer** (Required by DeepEval dependencies).
- Install dependencies (run from project root):
  ```bash
  python3.10 -m pip install -r requirements.txt
  ```
- Set up your **Gemini API Key**:
  ```bash
  export GEMINI_API_KEY="your-api-key"
  ```

## How to Run Evaluations

> [!IMPORTANT]
> All commands below should be run from the **project root** directory.

### 1. Running the Dataset Evaluation (Python)

To run evaluation on the full dataset defined in `pkg/evaluator/eval_data.json`:

```bash
export AGENT_TYPE="api" # Options: 'cli', 'api', 'mcp'
export AGENT_TARGET="gemini-2.5-flash" # Model name or path to binary
export PROJECT_ID="your-gcp-project"
export CLUSTER_NAME="your-cluster-name"

python3.10 pkg/evaluator/evaluate.py pkg/evaluator/eval_data.json
```

### 2. Running via Pytest

If you prefer to run the tests via Pytest (uses `pkg/evaluator/test_gke_agent.py`):

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3.10 -m pytest pkg/evaluator/test_gke_agent.py
```

### 3. Running via Go Integration

To test the Go wrapper (`pkg/agents/eval_agent.go`) calling the Python script:

Run the test file from the project root:
```bash
go run test_eval.go
```

## Metrics Used

- **OutcomeValidity**: Evaluates if the agent achieved the goal based on the rubric.
- **ToolInvocation**: Verifies if the agent used relevant tools.
