# Migration: Target directory structure and mapping

This document outlines the target layout for `devops-bench`, maps existing files in `gke-labs/devops-bench` (the *incubator*) to their new homes, and defines the high-level vocabulary used across the codebase.

### Documentation directory map
- For high-level steps for gke-labs maintainers, see [README.md](./README.md).
- For a deep dive into architectural designs and principles, see [component-design.md](./component-design.md).
- For the phased pull request deployment sequence, see [pr-plan.md](./pr-plan.md).
- For details on proving the plan using a local sandbox, see [VALIDATION.md](./VALIDATION.md).

---

## 1. Glossary: Framework terms

To prevent ambiguity, the codebase adheres to strict definitions for key framework structures:

| Term | What it is | Primary Location |
|------|------------|------------------|
| **Task** | A benchmark scenario defining an intent, infrastructure requirements, and success verifications. | `tasks/` (YAML definitions) |
| **Agent** | The AI system being evaluated. Powered by an **Agent Harness** adapter over a communication transport. | `devops_bench/agents/` |
| **Evaluation Harness** | The execution pipeline that orchestrates the lifecycle of a task (provisioning, scenario startup, running the agent, teardown, scoring). | `devops_bench/harness/` |
| **Scenario Manager** | A component within the evaluation harness that concurrently manages background chaos injection and checks. | `devops_bench/harness/scenario.py` |
| **Chaos** | Fault injection configured as a combination of a **Trigger** (when) and a **Fault** (what). | `devops_bench/chaos/` |
| **Verification** | Outcome assertions evaluated during or at the end of a scenario. Supports complex nested lists/dicts. | `devops_bench/verification/` |
| **Metric / Judge** | Rubrics used to grade the agent's run trajectory, usually LLM-as-judge. | `devops_bench/metrics/` |
| **Model / Provider** | Unified API access for LLM requests (consumed by API agents, chaos, and judges). | `devops_bench/models/` |
| **Deployer** | Software that provisions/destroys infrastructure by executing Terraform or Kind scripts. | `devops_bench/deployers/` |
| **Skill** | Runtime instructions, prompts, or checklists loaded by judges or BYO-skill agents. | `skills/` (Markdown documents) |

---

## 2. Target directory tree

We adopt a **flat repository layout** (without a nested `src/` directory) to conform to `kubernetes-sigs` standards. We maintain library integrity using editable installs (`uv sync`) and strict CI checks.

```
devops-bench/
├── .github/workflows/                 # CI Configurations
│   └── guardrails.yml                 # Main test and lint pipeline
├── devops_bench/                      # Primary package namespace (flat, at root)
│   ├── __init__.py
│   ├── core/                          # Primitives (registry, context, results, errors)
│   ├── tasks/                         # Task schema specifications and loader logic
│   ├── agents/                        # Target agents under evaluation
│   │   ├── base.py                    # AgentHarness base class & registry
│   │   ├── capabilities/              # Capability specs, mixins, and protocols
│   │   ├── cli/                       # Subprocess CLI transport agents (e.g., gemini)
│   │   ├── api/                       # API integration transport agents (e.g., mcp)
│   │   └── chat/                      # Conversation transport agents
│   ├── models/                        # LLM Provider integrations (Google, Anthropic)
│   ├── k8s/                           # Subprocess kubectl and watch wrappers
│   ├── deployers/                     # Terraform and Kind infrastructure engines
│   ├── harness/                       # Run orchestrator, ScenarioManager, and state
│   ├── chaos/                         # Fault injection triggers and actions
│   ├── verification/                  # Outcome check assertions and tree runner
│   ├── metrics/                       # LLM grading judges and score mapping
│   ├── reporting/                     # Results JSON aggregator and leaderboard feed
│   ├── cli.py                         # Command Line entrypoint handler
│   └── __main__.py
├── hack/                              # Development scripts (status, prep-export, etc.)
├── infra/                             # Shared Terraform modules and common stacks
│   ├── modules/                       # Reusable infrastructure blocks
│   └── stacks/                        # Reusable stack environments (local, common)
├── tasks/                             # Task definition data files (YAML + local infra)
├── skills/                            # Scoring guides and agent instructional prompts
├── tests/                             # Test suite (mirrors devops_bench/ layout)
│   ├── unit/                          # Unit tests (migrate with code)
│   └── integration/                   # Cross-cutting end-to-end integration tests
└── pyproject.toml                     # Modern package metadata and tool configs
```

> [!NOTE]
> **Planned Directories**: The `devops_bench/agents/capabilities/` subpackage is defined in the target architecture but is not part of the initial migration (it is deferred to keep the early PRs small). It will be developed directly upstream in `kubernetes-sigs` as a post-migration phase.

---

## 3. Current-to-target path mapping

This table maps every significant path in the legacy `gke-labs` repository to its restructured location inside the new `devops_bench` library.

| Legacy Path (gke-labs) | Restructured Path (devops_bench) | Notes |
|-----------------------|---------------------------------|-------|
| `pkg/evaluator/evaluate.py` (Main loop) | `devops_bench/harness/{base,default,artifacts}.py` | Decomposed into pipeline phases |
| `pkg/evaluator/evaluate.py` (Metrics) | `devops_bench/metrics/{pipeline,geval,outcome_validity,tool_invocation,grounding,chaos_metrics}.py` | Split into discrete metric modules |
| `pkg/evaluator/loader.py` | `devops_bench/tasks/loader.py` | |
| `pkg/manager/manager.py` | `devops_bench/harness/scenario.py` | ScenarioManager is part of the harness |
| `pkg/agents/chaos/chaos.py` | `devops_bench/chaos/agent.py` + `devops_bench/chaos/faults/generate_load.py` | Split into agent loop + fault action |
| `pkg/agents/verifier/*` | `devops_bench/verification/*` | Extracted into verifier base and registries |
| `pkg/agents/runner/gcli.py`, `openclaw.py` | `devops_bench/agents/cli/{gemini,openclaw}.py` | Relocated by transport |
| `pkg/agents/runner/api/{api,utils}.py`, `mcp_client.py` | `devops_bench/agents/api/{loop,mcp}.py` | |
| `pkg/agents/runner/api/{llm_client,llm_adapters}.py` | `devops_bench/models/{anthropic,google}.py` | Centralized LLM providers |
| `pkg/agents/runner/runner.py` | `devops_bench/agents/base.py` | Core AgentHarness class |
| `deployers/` (Top-level) | `devops_bench/deployers/` | Moved inside the python package namespace |
| `tf/` | `infra/` | Reorganized into modules and stacks |
| `tasks/` + `complextasks/` | `tasks/` | Merged into a unified tasks directory |
| `skills/` (In legacy paths) | `skills/` | Relocated to repo root as content data |
| `scripts/entrypoint.sh` | `hack/entrypoint.sh` | CLI-wrapping shell helpers |

---

## 4. Out-of-scope files (gke-labs only)

These files represent public web assets and gke-labs-specific CI deployment scripts. They remain exclusively in the `gke-labs` repository and will **not** be exported to `kubernetes-sigs`:

- `site/` (Web dashboard frontend)
- `site_new/`
- `.github/workflows/static.yml` (Dashboard deployment pipeline)
