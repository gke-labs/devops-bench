# Running kube-agents evals via a library dependency on kubernetes-sigs/devops-bench

**Goal.** Decouple kube-agents from the devops-bench source tree. Today, kube-agents'
Prow CI (`hack/ci-eval-pr.sh`) runs the legacy evaluator (`/app/pkg/evaluator/evaluate.py`,
`AGENT_TARGET=kubeagents`) baked into a container image. Instead, kube-agents
pip-installs `kubernetes-sigs/devops-bench` as a library, implements its agent harness in
its own repo, and authors its own tasks — so both teams ship independently.

**Status.** The sigs repo is a complete, pip-installable library: the full `devops_bench/`
package including the eval harness, and (as of PR #41, commit `bef4468`) the
`devops-bench` CLI / `run_benchmark()` entrypoint. No PyPI release yet — pin a git SHA.

## Prerequisites in devops-bench (two small PRs)

1. **Entry-point discovery for agents.** `AGENTS` in `devops_bench/agents/base.py` is
   built without an entry-point group (unlike verifiers/providers/metrics, which have
   one). Change to `Registry("agents", entry_point_group="devops_bench.agents")`. Until
   this lands, kube-agents must call `run_benchmark()` from a small driver script that
   first imports their agent module.
2. **Overridable TF stack root.** `deployers/tofu.py` resolves relative stack names
   against `Path(__file__).parents[2]/"tf"`, which breaks under pip install. Add an
   env/config override (e.g. `BENCH_TF_ROOT`). Interim workaround: absolute `stack:`
   paths in task.yaml (note: absolute stacks skip per-run isolation, so avoid concurrent
   runs sharing one stack dir).

## Implementation in kube-agents

**1. Dependency** — `devops-bench @ git+https://github.com/kubernetes-sigs/devops-bench@<sha>`
(Python ≥ 3.12).

**2. Agent harness** (~150 lines, a port of legacy `pkg/agents/runner/kubeagents.py`):

```python
from devops_bench.agents import AGENTS, AgentHarness, AgentResult, ToolCall

@AGENTS.register("kubeagents")
class PlatformAgentHarness(AgentHarness):
    def _execute(self, prompt, workspace_path=None) -> AgentResult:
        # 1. ensure kubectl port-forward to svc/platform-agent (or in-cluster URL)
        # 2. POST {model, conversation, input: prompt} to /v1/responses, Bearer token
        # 3. map output: assistant text -> result.output;
        #    function_call / function_call_output pairs -> ToolCall trajectory;
        #    usage -> tokens. Known errors -> result.errors (don't raise).
```

The base class provides latency stamping, crash containment, and optional deepeval
tracing. Declare the entry point so the console script discovers it once prerequisite 1
lands:

```toml
[project.entry-points."devops_bench.agents"]
kubeagents = "kube_agents_evals.harness:PlatformAgentHarness"
```

**3. Tasks** — an `evals/tasks/` dir of `task.yaml` files (the loader accepts any
directory or single file; schema is `devops_bench.tasks.schema.Task`). Copy
`gpu-stress-test-diagnosis` and its `tf/prebuilt/gpu-stress-test` stack from devops-bench
as the seed. Use `deployer: noop` / `--no-infra` tasks where possible; real-infra tasks
need a stack path (absolute until prerequisite 2 lands).

**4. CI swap** in `hack/ci-eval-pr.sh`: keep the cluster auth, token fetch, and TF_VAR
exports; replace the evaluator invocation with:

```bash
pip install "devops-bench @ git+https://github.com/kubernetes-sigs/devops-bench@<sha>" kube-agents-evals/
devops-bench evals/tasks/gpu-stress-test-diagnosis/task.yaml \
  --agent-type kubeagents --project "$PROJECT_ID" --cluster test-cluster --parallel
```

Env carries over: `AGENT_SERVICE_NAME`, `AGENT_NAMESPACE`, `AGENT_CLUSTER_CONTEXT`,
`PLATFORM_AGENT_TOKEN`, `JUDGE_PROVIDER`/`JUDGE_MODEL`/`JUDGE_API_KEY`. Drop
`AGENT_TARGET`/`BENCH_AGENT_TYPE=cli` (replaced by `--agent-type kubeagents`). Results
land in `results/run_*/results.json` (same score-gate parsing).

## Acceptance

- `devops-bench <noop task> --no-infra --agent-type kubeagents` passes against a
  port-forwarded platform-agent from a clean venv (no devops-bench checkout).
- The Prow smoke test passes with the OutcomeValidity ≥ 0.7 gate unchanged.
- devops-bench then deletes legacy `pkg/agents/runner/kubeagents.py` with no kube-agents
  breakage.
