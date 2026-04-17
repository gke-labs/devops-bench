# DevOps Bench

Devops-bench is a benchmark for assessing the performance of agents on a diverse set of DevOps tasks. While existing benchmarks often focus on isolated code generation or simple API calls, `Devops-bench` evaluates AI agents on their ability to perform  (devops) tasks for developers / platform engineers that require critical reasoning and state observation.

The goal is to measure and compare the capability of different agents in completing DevOps workflows. We aim to quantify the value of providing agents with rich environment context, specific operational rules, and specialized tools.


## Live Benchmark Results

See live leaderboard for the latest benchmark results. The data evaluates the following two distinct agent configurations (more to come later) to measure the value-add of domain-specific enhancements.

**Antigravity Agent**
Antigravity agent operates using the default configurations and prompts without advanced cloud-specific auxiliary intelligence or specialized guardrails. It serves as the baseline for performance, focusing on the agent's ability to execute raw Kubernetes tasks.

**Antigravity Agent with GCA and GKE special skills and tools**
The augmented agent integrates layers of optimization to improve reliability and architectural soundness:

* **GCA (Gemini Cloud Assist)**: Leverages specialized cloud knowledge tools.
* **Rules & Custom Instructions**: Instructions that help the agent to adhere to best practices.

## Task Selection

While our initial results are centered on the scale and sophistication of **Google Kubernetes Engine (GKE)**, this benchmark is designed for the entire cloud-native ecosystem. Whether you are operating on-premises, across hybrid clouds, or on various managed offerings, the fundamental challenges of agentic operations remain the same:

* **Intent to Infrastructure**: Can an agent translate a high-level requirement into a secure, scalable deployment?

* **Autonomous Operations**: How effectively can an agent maintain the "desired state" in an unpredictable environment?

* **Proactive Troubleshooting**: Can an agent move from detecting a pod failure to diagnosing the root cause and executing a fix?

The benchmark currently consists of 5 tasks simulating realistic deployment scenarios, which we plan to expand further.  You can learn more about the tasks here.

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

You can look at the actual Skill based rubrics here.

## Running Benchmarks locally
Evaluations can be performed by running the benchmark tasks against your agent and manually or programmatically applying the LLM-as-a-judge method using the Skill based rubrics provided in this repository.

### Step 1: Set up the agent
You can configure the agent in two ways depending on the capabilities you want to test: 
* **Option 1**: Using only the core Antigravity agent
This configuration uses the core agent capabilities without external cloud assistance.
* **Option 2**: Antigravity + Gemini Cloud Assist via the Model Context Protocol (MCP) with agent rules.
This configuration connects your agent to Gemini Cloud Assist for broader cloud management capabilities.

### Step 2: Run tasks with your agent
Feed each task to your configured agent and capture the agent's final response for each task, and ideally a trace of the execution steps (tools called, reasoning steps).

### Step 3: Evaluate Responses with LLM-as-a-Judge
To evaluate the results, use a capable LLM to score the agent's responses against the specific criteria defined in the repository's skills directory.

* **Choose a Judge Model**: Select a powerful LLM to act as your judge (e.g., Gemini 2.5 Pro or similar).
**Note**: The results in this repository use gemini-3-flash-preview for outcome evaluation.

* **Construct the Judge Prompt**: For each of the 5 tasks, construct a prompt (using the SKILL template) for the judge LLM. The prompt should include:
    * The original User Prompt/Task.
    * The Agent's Response (and execution trace if evaluating tool usage).
    * The relevant Skill Rubric (copy the content from the appropriate SKILL.md file).
* **Query the Judge**: Send the prompt to the judge LLM.
* **Extract Scores**: Parse the judge's output to collect the numerical score and the justification.
