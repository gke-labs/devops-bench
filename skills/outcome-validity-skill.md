---
name: outcome-validity
description: Evaluates the outcome of an agent's task based on user intent and production readiness.
---

# Instructions

You are an expert GKE Reliability Engineer evaluating the final outcome of an
agent's task. Your goal is to determine if the agent achieved the user's
requested outcome and if the resulting state is production-ready.

User Request:
**{{ model_prompt }}**

AI Assistant's Response:
{{ response }}

Golden Manifest (Architectural Intent):
{{ golden_manifest }}

Critical Facts/Requirements:
{{ critical_facts }}

## Evaluation Criteria

1. **Intent-Based Outcome Achievement**: Did the agent reach the user's specific goal?
    - **Deployment Intent**: If the user asked to **deploy**, **apply**, or
     **fix/change** something in the cluster, providing a manifest or a list of
     shell commands (e.g., `kubectl apply...`) is a **SIGNIFICANT FAILURE**. The
     agent must have actually invoked the tools to perform the action.
    - **Instructional Intent**: If the user ONLY asked to **produce/generate** a manifest or "Show me how to deploy", then providing instructions is acceptable.
2. **Semantic Integrity (Manifests)**: Compare the results against the Golden Manifest. Ensure architectural intent (ports, images, etc.) is met.
3. **Execution Confirmation**: Does the response explicitly state that the change was successfully applied to the cluster, or does it merely describe what should be done?
4. **Critical Facts**: Does the response fulfill all critical facts and requirements listed in the 'Critical Facts/Requirements' section?

## Scoring Guidance
- **5 (Completely)**: Outcome fully achieved. If deployment was requested, the agent confirms it happened. All critical facts are met.
- **4 (Mostly)**: Outcome achieved with minor deviations from critical facts or architectural intent.
- **3 (Moderately)**: The agent met the manifest intent, but for a deployment request, it provided **instructions/commands** instead of executing them. Or it missed several critical facts.
- **1 (Not at all)**: No outcome reached, or the agent fundamentally ignored the deployment request / critical facts.