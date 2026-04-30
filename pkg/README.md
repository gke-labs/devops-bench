# GKE Agent Evaluation Suite

This directory contains evaluation suite logic for the GKE Agent, using DeepEval.

## Prerequisites

- **Python 3.10 or newer** (Required by DeepEval dependencies).
- Load dependencies (run from project root):
  ```bash
  source .venv/bin/activate
  python3 -m pip install -r requirements.txt
  ```
- Set up your **Gemini API Key**:
  ```bash
  export GEMINI_API_KEY="your-api-key"
  ```

## How to Run Evaluations

> [!IMPORTANT]
> All commands below should be run from the **project root** directory.

### 1. Running the Dataset Evaluation (Python)

To run evaluation on tasks definitions dynamically located in the tasks directory:

```bash
source .venv/bin/activate
export AGENT_TYPE="api" # Options: 'cli', 'api'
export AGENT_TARGET="gemini-2.5-flash" # Model name or path to binary
export PROJECT_ID="your-gcp-project"
export CLUSTER_NAME="your-cluster-name"

python3 pkg/evaluator/evaluate.py tasks/
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

