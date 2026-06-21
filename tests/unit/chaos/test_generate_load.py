# Copyright 2026 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for GenerateLoadFault — inject path, command runner, system prompt.

The port-forward the load fault uses to reach its target lives in this fault
(#33): :meth:`GenerateLoadFault.inject` opens its own ``kubectl port-forward``,
points the load URL at the local tunnel, and tears the tunnel down — so the
port-forward lifecycle is covered here, not in the harness scenario tests.
"""

from __future__ import annotations

import threading
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch

from devops_bench.chaos.base import ChaosResult
from devops_bench.chaos.faults import generate_load as gl
from devops_bench.chaos.faults.generate_load import (
    _ENV_SKIP_PORT_FORWARD,
    _ENV_TARGET_DEPLOYMENT,
    _ENV_TARGET_NAMESPACE,
    GenerateLoadFault,
    LoadTarget,
    build_system_instruction,
    run_chaos_command,
)
from devops_bench.core.context import RunContext


def _make_ctx(env: dict[str, str] | None = None) -> RunContext:
    return RunContext(task_id="test", env=env or {})


def test_build_system_instruction_embeds_target_url():
    msg = build_system_instruction("http://localhost:9999")
    assert "http://localhost:9999" in msg
    assert "fortio" in msg


def test_run_chaos_command_rejects_empty_command():
    assert run_chaos_command("   ") == "Error: command string is empty"


def test_run_chaos_command_sets_event_only_on_load_marker():
    event = threading.Event()
    fake = CompletedProcess(args=["fortio"], returncode=0, stdout="OUT", stderr="ERR")
    with patch.object(gl, "run", return_value=fake) as run_mock:
        out = run_chaos_command("fortio load -qps 50 http://x", chaos_active_event=event)

    assert event.is_set()
    assert "Stdout:\nOUT" in out
    assert "Stderr:\nERR" in out
    # shlex-split argv reached the executor, not a shell string.
    argv = run_mock.call_args.args[0]
    assert argv[0] == "fortio"
    assert argv[1:3] == ["load", "-qps"]


def test_run_chaos_command_does_not_set_event_for_unrelated_command():
    event = threading.Event()
    fake = CompletedProcess(args=["kubectl"], returncode=0, stdout="x", stderr="")
    with patch.object(gl, "run", return_value=fake):
        run_chaos_command("kubectl get pods", chaos_active_event=event)
    assert not event.is_set()


def test_run_chaos_command_surfaces_executor_exception_as_error_string():
    with patch.object(gl, "run", side_effect=RuntimeError("boom")):
        out = run_chaos_command("fortio load http://x")
    assert out.startswith("Error: ")
    assert "boom" in out


def test_inject_returns_chaos_result_on_success():
    fault = GenerateLoadFault(
        target=LoadTarget(service_url="http://localhost:8080", qps=50)
    )

    # Patch the ChaosAgent the fault constructs so no model / SDK / network runs.
    class _StubAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self, goal: str) -> str:
            assert "http://localhost:8080" in goal  # goal carries the rewritten URL
            return "spike complete"

    # ``ChaosAgent`` is imported lazily inside ``inject`` (Phase 4 keeps the
    # agent + models chain out of sys.modules until injection runs), so the
    # patch must target the source module rather than the fault module.
    with patch("devops_bench.chaos.agent.ChaosAgent", _StubAgent):
        result = fault.inject(_make_ctx())

    assert isinstance(result, ChaosResult)
    assert result.success is True
    assert result.injected_fault == "generate_load"
    assert result.output == "spike complete"
    assert result.elapsed_time >= 0.0
    assert result.error is None


def test_inject_converts_agent_failure_to_failed_chaos_result():
    fault = GenerateLoadFault(target=LoadTarget(service_url="http://x", qps=1))

    class _BoomAgent:
        def __init__(self, **kwargs):
            pass

        def run(self, goal: str) -> str:
            raise RuntimeError("model offline")

    with patch("devops_bench.chaos.agent.ChaosAgent", _BoomAgent):
        result = fault.inject(_make_ctx())

    assert result.success is False
    assert result.injected_fault == "generate_load"
    assert result.error is not None
    assert "model offline" in result.error


def test_inject_threads_chaos_active_event_through_to_agent():
    fault = GenerateLoadFault(target=LoadTarget(service_url="http://x", qps=1))
    event = threading.Event()

    captured: dict = {}

    class _CapturingAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self, goal: str) -> str:
            return "ok"

    with patch("devops_bench.chaos.agent.ChaosAgent", _CapturingAgent):
        fault.inject(_make_ctx(), chaos_active_event=event)

    assert captured["chaos_active_event"] is event
    assert captured["tool"] is gl.RUN_COMMAND_TOOL
    assert captured["tool_handler"] is gl.run_chaos_command
    # The system instruction targets the rewritten URL from the spec.
    assert "http://x" in captured["system_instruction"]


def test_goal_dumps_spec_with_target_url():
    fault = GenerateLoadFault(target=LoadTarget(service_url="http://svc", qps=42))
    goal = fault.goal()
    assert "generate_load" in goal
    assert "http://svc" in goal
    assert "42" in goal


# -- port-forward lifecycle (moved from the harness scenario tests, #33) ------


def _live_popen() -> MagicMock:
    """A fake ``Popen`` that looks like a healthy, still-running tunnel."""
    proc = MagicMock()
    proc.poll.return_value = None  # still running after the settle window
    proc.returncode = None
    return proc


def test_inject_opens_port_forward_and_points_url_at_local_tunnel():
    """With a target deployment on ``ctx.env``, inject port-forwards + rewrites URL.

    The agent must see ``http://localhost:8080`` (the tunnel), not the
    in-cluster URL, and the tunnel must be terminated when injection finishes.
    """
    fault = GenerateLoadFault(
        target=LoadTarget(service_url="http://example.svc.cluster.local", qps=50)
    )
    proc = _live_popen()
    captured: dict = {}

    class _StubAgent:
        def __init__(self, **kwargs):
            captured["system_instruction"] = kwargs["system_instruction"]

        def run(self, goal: str) -> str:
            captured["goal"] = goal
            captured["url_during_run"] = fault.target.service_url
            return "spike complete"

    ctx = _make_ctx(
        {_ENV_TARGET_DEPLOYMENT: "web-app", _ENV_TARGET_NAMESPACE: "prod"}
    )
    with (
        patch.object(gl.subprocess, "Popen", return_value=proc) as popen_mock,
        patch.object(gl.time, "sleep"),  # don't actually sleep the settle window
        patch("devops_bench.chaos.agent.ChaosAgent", _StubAgent),
    ):
        result = fault.inject(ctx)

    # Port-forward opened against the threaded deployment / namespace.
    popen_mock.assert_called_once()
    pf_cmd = popen_mock.call_args.args[0]
    assert pf_cmd[:3] == ["kubectl", "port-forward", "deployment/web-app"]
    assert "prod" in pf_cmd
    assert pf_cmd[3] == "8080:8080"

    # The agent saw the local tunnel URL, both in the system prompt and the
    # goal, while the tunnel was open.
    assert "http://localhost:8080" in captured["system_instruction"]
    assert "http://localhost:8080" in captured["goal"]
    assert captured["url_during_run"] == "http://localhost:8080"

    # Tunnel torn down; the fault's stored URL restored afterwards.
    proc.terminate.assert_called_once()
    proc.wait.assert_called()
    assert fault.target.service_url == "http://example.svc.cluster.local"

    assert result.success is True
    assert result.output == "spike complete"


def test_inject_early_port_forward_exit_becomes_failed_result():
    """A port-forward that dies in the settle window yields a failed ChaosResult."""
    fault = GenerateLoadFault(
        target=LoadTarget(service_url="http://x.svc.cluster.local", qps=1)
    )
    dead = MagicMock()
    dead.poll.return_value = 1  # exited during the settle window
    dead.returncode = 1

    ctx = _make_ctx({_ENV_TARGET_DEPLOYMENT: "web-app"})
    with (
        patch.object(gl.subprocess, "Popen", return_value=dead),
        patch.object(gl.time, "sleep"),
        # The agent must never be constructed when the tunnel fails to come up.
        patch(
            "devops_bench.chaos.agent.ChaosAgent",
            side_effect=AssertionError("agent ran despite dead port-forward"),
        ),
    ):
        result = fault.inject(ctx)

    assert result.success is False
    assert result.error is not None
    assert "port-forward exited early" in result.error


def test_inject_skips_port_forward_when_flagged():
    """``CHAOS_SKIP_PORT_FORWARD`` runs the loop against the existing URL, no Popen."""
    fault = GenerateLoadFault(
        target=LoadTarget(service_url="http://existing", qps=1)
    )
    captured: dict = {}

    class _StubAgent:
        def __init__(self, **kwargs):
            captured["system_instruction"] = kwargs["system_instruction"]

        def run(self, goal: str) -> str:
            captured["url_during_run"] = fault.target.service_url
            return "ok"

    ctx = _make_ctx(
        {
            _ENV_TARGET_DEPLOYMENT: "web-app",
            _ENV_SKIP_PORT_FORWARD: "1",
        }
    )
    with (
        patch.object(gl.subprocess, "Popen") as popen_mock,
        patch("devops_bench.chaos.agent.ChaosAgent", _StubAgent),
    ):
        result = fault.inject(ctx)

    popen_mock.assert_not_called()
    # Skip flag means no rewrite — the agent targets the spec's own URL.
    assert captured["url_during_run"] == "http://existing"
    assert "http://existing" in captured["system_instruction"]
    assert result.success is True


def test_inject_without_target_deployment_runs_against_existing_url():
    """No deployment on ``ctx.env`` -> no port-forward, existing URL preserved."""
    fault = GenerateLoadFault(target=LoadTarget(service_url="http://plain", qps=1))
    captured: dict = {}

    class _StubAgent:
        def __init__(self, **kwargs):
            pass

        def run(self, goal: str) -> str:
            captured["url_during_run"] = fault.target.service_url
            return "ok"

    with (
        patch.object(gl.subprocess, "Popen") as popen_mock,
        patch("devops_bench.chaos.agent.ChaosAgent", _StubAgent),
    ):
        result = fault.inject(_make_ctx())

    popen_mock.assert_not_called()
    assert captured["url_during_run"] == "http://plain"
    assert result.success is True
