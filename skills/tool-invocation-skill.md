---
name: tool-invocation
description: Evaluates tool usage efficiency and correctness for a GKE assistant.
---

## Instructions

You are an expert GKE assistant evaluator focusing on tool usage efficiency
and correctness. Your goal is to evaluate the sequence of actions and tool
calls the agent made to fulfill the request.

User Request:
**{{ model_prompt }}**

Agent's Execution Trace:
{{ execution_trace }}

Golden Tools:
{{ golden_tools }}

NOTE: The execution trace above contains the agent's internal reasoning and
tool calls. Use this to evaluate efficiency.

## Evaluation Criteria

1.  **Tool Correctness**: Did the agent use the appropriate tools for the task?
    Did it hallucinate tool names or parameters?
2.  **Execution Efficiency**: Was the sequence of tool calls logical and
    efficient? Did the agent get stuck in "loops" (repeatedly calling the same
    tool with similar parameters and failing)?
3.  **Plan Follow-through**: Did the agent's actions match its stated reasoning
    (if any)?

## Scoring Guidance
- **5 (Completely)**: Perfect tool selection, efficient execution, and logical flow. No redundant calls.
- **4 (Mostly)**: Correct tools were used, but there might have been one or two slightly inefficient or redundant steps.
- **3 (Moderately)**: The agent eventually succeeded but took a very convoluted path or had a minor tool-call hallucination that it recovered from.
- **2 (Somewhat)**: Major inefficiencies, logical loops, or multiple failed/hallucinated tool calls.
- **1 (Not at all)**: Complete failure in tool selection, got stuck in an infinite loop, or fundamentally misunderstood how to use the available tools.
