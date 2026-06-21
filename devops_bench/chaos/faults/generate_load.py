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

"""The ``generate_load`` fault: LLM-driven fortio traffic spikes.

This module owns every fortio-specific concern: the load-target schema, the SRE
system prompt, the ``run_command`` tool descriptor, the shell-free argv
executor, the ``kubectl port-forward`` lifecycle, and the typed
:class:`GenerateLoadFault` node. The chaos agent is imported lazily inside
:meth:`GenerateLoadFault.inject` so registering this fault does not pull the
agent or :mod:`devops_bench.models` chain.
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import subprocess
import textwrap
import threading
import time
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any, Literal

from pydantic import BaseModel, Field

from devops_bench.chaos.base import FAULTS, ChaosResult, Fault
from devops_bench.core import get_logger
from devops_bench.core.context import RunContext
from devops_bench.core.subprocess import run

__all__ = [
    "GenerateLoadFault",
    "LoadTarget",
    "RUN_COMMAND_TOOL",
    "build_system_instruction",
    "run_chaos_command",
]

_log = get_logger("chaos.generate_load")

# Marker substring that, when present in a command, indicates a load spike is
# active. The harness watches the shared event to coordinate measurements.
_LOAD_MARKER = "fortio load"

# Wall-clock ceiling for a single chaos command.
_COMMAND_TIMEOUT = 40

# Local port the cluster workload is exposed on for chaos load generation.
_LOCAL_PORT = 8080

# Single source of truth for the load target when a spec omits one. The local
# port-forward URL the cluster workload is exposed on.
_DEFAULT_TARGET_URL = f"http://localhost:{_LOCAL_PORT}"

# Seconds to let ``kubectl port-forward`` establish the tunnel before load.
_PORT_FORWARD_SETTLE_SEC = 3

# ``RunContext.env`` keys naming the port-forward target the harness writes
# onto the context before injection.
_ENV_TARGET_DEPLOYMENT = "CHAOS_TARGET_DEPLOYMENT"
_ENV_TARGET_NAMESPACE = "CHAOS_TARGET_NAMESPACE"
_ENV_SKIP_PORT_FORWARD = "CHAOS_SKIP_PORT_FORWARD"


def build_system_instruction(target_url: str = _DEFAULT_TARGET_URL) -> str:
    """Build the SRE system instruction, targeting ``target_url`` for load.

    Args:
        target_url: URL fortio load should be directed at. Flows from the
            fault's ``target.service_url`` (rewritten by the harness to the
            local port-forward), defaulting to :data:`_DEFAULT_TARGET_URL`.

    Returns:
        The system instruction string with the target URL injected.
    """
    # Each paragraph the model sees is one physical source line; ``dedent``
    # strips the shared leading indentation.
    return textwrap.dedent(
        f"""\
        You are a professional Site Reliability Engineer (SRE) and Chaos Engineering Expert.
        Your role is to disrupt GKE workloads to test system resilience, which can happen in two modes:
        1. Planned Mode: Execute a specific GKE chaos disruption according to a provided JSON spec.
        2. Autonomous Mode: Autonomously explore the GKE cluster state, identify critical targets (pods, nodes, services), and inject transient faults to test recovery.

        You are equipped with the `run_command` tool, which runs a single command locally on the GKE host control machine (which is fully authenticated and has GKE admin kubectl privileges). Each call must be ONE non-piped command: shell pipelines, redirection, command chaining (``|``, ``>``, ``&&``, ``;``) and environment-variable interpolation (``$VAR``) are NOT supported.

        Strict Guidelines for Execution:
        - Single Execution Policy: You MUST execute exactly one tool call to run the planned 'fortio' load generation spike. Do NOT attempt to rerun, adjust, or tune the load generation if the target service saturates or returns timeouts. Once the single load command is executed, analyze the output, write your final performance summary, and exit immediately.
        - Safety First: Only inject transient, safe, and recoverable faults (e.g. killing pods, scaling deployments, generating traffic spikes). Do NOT permanently destroy GKE clusters, namespaces, or nodes.
        - Traffic Generation: For load spikes, use the 'fortio' binary. Since GKE internal service URLs (*.svc.cluster.local) are port-forwarded to the host, you MUST target '{target_url}' instead.
        - Analysis & Clarity: Analyze command outputs carefully, report stdout/stderr accurately, and confirm in your final response when the disruption has been successfully completed."""
    )


# Neutral, duck-typed tool descriptor consumed by ``LLMClient.format_tools``
# (mirrors the MCP tool shape: name/description/inputSchema).
RUN_COMMAND_TOOL = SimpleNamespace(
    name="run_command",
    description=(
        "Run a shell command on the GKE host control machine (authenticated kubectl + fortio). "
        "Returns combined stdout and stderr."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute, e.g. a fortio load invocation.",
            }
        },
        "required": ["command"],
    },
)


def run_chaos_command(
    command: str,
    chaos_active_event: threading.Event | None = None,
) -> str:
    """Execute a single chaos command and return its combined output.

    The command is a single, non-piped string produced by the LLM (typically a
    ``fortio load`` invocation). It is tokenized with :func:`shlex.split` and
    run shell-free, so shell features (pipes, redirection, ``$VAR``) are not
    supported; a leading ``~`` in each token is expanded to the user's home.
    When the command is a load spike and an event is supplied, the event is
    set so the harness can observe that load is active before measuring impact.

    Args:
        command: Single command to execute (no shell pipelines or redirection).
        chaos_active_event: Optional event signaled when a load spike starts.

    Returns:
        A string combining stdout and stderr, or an ``"Error: ..."`` string if
        the command could not be parsed or run.
    """
    if not command.strip():
        return "Error: command string is empty"

    try:
        _log.info("running chaos command: %s", command)

        # The model emits shell strings (e.g. a single fortio invocation); split
        # into argv so execution stays shell-free. shlex.split does not expand
        # ``~``, so expand each token's leading home to keep ``~/go/bin/fortio``
        # style paths resolvable.
        argv = [os.path.expanduser(arg) for arg in shlex.split(command)]

        # Signal "load active" only once the command parses cleanly and we are
        # about to execute it, so a parse failure never falsely tells the
        # harness that load is live.
        if chaos_active_event is not None and _LOAD_MARKER in command:
            _log.info("load spike detected; signaling harness via chaos event")
            chaos_active_event.set()

        completed = run(argv, check=False, timeout=_COMMAND_TIMEOUT)
        return f"Stdout:\n{completed.stdout}\nStderr:\n{completed.stderr}"
    except Exception as exc:  # noqa: BLE001 - surface any failure back to the LLM
        return f"Error: {exc}"


@contextlib.contextmanager
def _port_forward(deployment: str, namespace: str, local_port: int) -> Iterator[None]:
    """Hold a ``kubectl port-forward`` open for the body, then tear it down.

    The port-forward is held open for the duration of load generation, so it
    uses :func:`subprocess.Popen` directly rather than the one-shot
    ``core.subprocess.run`` helper. ``stdout`` / ``stderr`` go to ``DEVNULL``
    because nothing reads the pipes — ``PIPE`` would let ``kubectl`` block once
    its output buffer fills under sustained load. The tunnel is always
    terminated on exit, whether the body completes or raises, so it never
    outlives the injection.

    Args:
        deployment: Name of the deployment to forward (``deployment/<name>``).
        namespace: Namespace the deployment lives in.
        local_port: Local port mapped to the same port on the workload.

    Yields:
        ``None`` once the tunnel has had time to settle.

    Raises:
        RuntimeError: If ``kubectl port-forward`` exits before the settle
            window elapses (e.g. the deployment does not exist).
    """
    _log.info(
        "establishing port-forward to deployment/%s on port %d...",
        deployment,
        local_port,
    )
    pf_cmd = [
        "kubectl",
        "port-forward",
        f"deployment/{deployment}",
        f"{local_port}:{local_port}",
        "-n",
        namespace,
    ]
    process = subprocess.Popen(
        pf_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    time.sleep(_PORT_FORWARD_SETTLE_SEC)
    if process.poll() is not None:
        # Reap the already-exited child before raising so it does not linger as
        # a zombie waiting for ``wait()``. ``terminate`` is a no-op on a
        # process that already exited; ``wait`` collects the exit status.
        returncode = process.returncode
        try:
            process.wait(timeout=_PORT_FORWARD_SETTLE_SEC)
        except Exception as exc:  # noqa: BLE001 - never mask the raise reason
            _log.warning("error reaping early-exited port-forward: %s", exc)
        raise RuntimeError(
            f"kubectl port-forward exited early (code {returncode}) "
            f"for deployment/{deployment} in {namespace!r}"
        )

    try:
        yield
    finally:
        _log.info("terminating GKE port-forward...")
        process.terminate()
        process.wait()
        _log.info("port-forward terminated.")


class LoadTarget(BaseModel):
    """Target for a generated load spike.

    Attributes:
        service_url: HTTP URL the load should be directed at. When the fault
            opens its own port-forward (see :meth:`GenerateLoadFault.inject`),
            this in-cluster ``*.svc.cluster.local`` URL is pointed at the local
            tunnel for the duration of injection.
        qps: Target queries per second; the LLM passes this to fortio.
        duration: Optional fortio duration string (e.g. ``"30s"``). When
            omitted, the model picks one consistent with the goal.
        concurrency: Optional fortio ``-c`` concurrency override.
    """

    service_url: str
    qps: int = Field(default=100, ge=1)
    duration: str | None = None
    concurrency: int | None = Field(default=None, ge=1)


@FAULTS.register("generate_load")
class GenerateLoadFault(Fault):
    """A traffic-spike fault driven by an LLM issuing fortio commands.

    The fault exposes a single command-execution capability to the model and
    relies on the agent loop to plan and issue exactly one ``fortio load``
    spike against the port-forwarded target. The fault owns the connectivity:
    :meth:`inject` opens its own ``kubectl port-forward`` to the target
    deployment, points the load URL at the local tunnel, and tears the tunnel
    down when injection completes.

    Attributes:
        type: Discriminator literal, always ``"generate_load"``.
        target: Typed load-target description (URL, qps, optional duration /
            concurrency).
    """

    type: Literal["generate_load"] = "generate_load"
    target: LoadTarget

    def goal(self) -> str:
        """Build the planned-mode goal prompt for the LLM.

        The target URL is read from :attr:`target`; :meth:`inject` points it at
        the local port-forward for the duration of injection, so the model's
        prompt always agrees with the URL the load actually hits.

        Returns:
            The goal prompt instructing the model to issue one fortio spike.
        """
        spec_dump: dict[str, Any] = self.model_dump(exclude_none=True)
        target_url = self.target.service_url
        spec_json = json.dumps(spec_dump, indent=2)
        # Dedent the template BEFORE interpolating ``spec_json``: the dumped
        # JSON is multi-line with no shared leading indentation, so substituting
        # it first would defeat ``dedent``'s common-prefix strip.
        template = textwrap.dedent(
            """\
            Your goal is to execute the following GKE planned chaos engineering disruption action:
            ```json
            {spec_json}
            ```

            Guidelines for execution:
            1. Use the 'fortio' tool to inject traffic into GKE.
            2. Note: GKE service target URLs (like *.svc.cluster.local) are port-forwarded to '{target_url}' on the host, so run fortio against {target_url} instead.
            Use your run_command tool to execute this disruption safely and effectively."""
        )
        return template.format(spec_json=spec_json, target_url=target_url)

    def inject(
        self,
        ctx: RunContext,
        chaos_active_event: threading.Event | None = None,
    ) -> ChaosResult:
        """Open a port-forward, run the LLM-planned chaos loop, tear it down.

        The fault owns its own connectivity: when the run context names a
        target deployment (via :data:`_ENV_TARGET_DEPLOYMENT` /
        :data:`_ENV_TARGET_NAMESPACE` on ``ctx.env``) and the port-forward is
        not skipped, :meth:`inject` opens a ``kubectl port-forward`` to that
        deployment, points the load URL at ``http://localhost:<port>`` for the
        duration of injection, generates load, and tears the tunnel down in a
        ``finally``. When the deployment is absent or
        :data:`_ENV_SKIP_PORT_FORWARD` is set (E2E smoke / unit tests), it runs
        the chaos loop against whatever URL the target already carries.

        Args:
            ctx: Run context; ``ctx.env`` carries the port-forward target the
                harness threaded in (deployment, namespace, skip flag).
            chaos_active_event: Optional event the executor signals when a
                load spike starts, so the harness can synchronize measurements.

        Returns:
            A :class:`ChaosResult` whose ``success`` is True on a clean loop
            completion. Exceptions raised by the agent or the port-forward are
            converted to ``success=False`` with the failure surfaced in
            ``error``.
        """
        env = ctx.env or {}
        deployment = env.get(_ENV_TARGET_DEPLOYMENT)
        namespace = env.get(_ENV_TARGET_NAMESPACE, "default")
        skip_port_forward = bool(env.get(_ENV_SKIP_PORT_FORWARD))

        start = time.monotonic()
        # Open the fault's own tunnel only when a target deployment is named and
        # the caller did not opt out; otherwise run against the existing URL.
        if deployment and not skip_port_forward:
            forward = _port_forward(deployment, namespace, _LOCAL_PORT)
            local_url: str | None = _DEFAULT_TARGET_URL
        else:
            forward = contextlib.nullcontext()
            local_url = None

        try:
            with forward:
                output = self._run_agent_loop(local_url, chaos_active_event)
        except Exception as exc:  # noqa: BLE001 - one fault must never abort the run
            elapsed = time.monotonic() - start
            _log.exception("generate_load fault crashed")
            return ChaosResult(
                success=False,
                injected_fault=self.type,
                output="",
                elapsed_time=elapsed,
                error=f"{type(exc).__name__}: {exc}",
            )
        elapsed = time.monotonic() - start
        return ChaosResult(
            success=True,
            injected_fault=self.type,
            output=output,
            elapsed_time=elapsed,
        )

    def _run_agent_loop(
        self,
        local_url: str | None,
        chaos_active_event: threading.Event | None,
    ) -> str:
        """Drive the chaos agent against the effective target URL.

        When ``local_url`` is set the fault is reaching its target through a
        port-forward, so the load URL is pointed at the local tunnel for the
        duration of the loop (and restored afterwards) — this keeps both the
        system instruction and the goal prompt agreeing with the URL the load
        actually hits. When ``local_url`` is ``None`` the existing target URL is
        used unchanged.

        Args:
            local_url: Local port-forward URL to target, or ``None`` to use the
                target's own ``service_url``.
            chaos_active_event: Optional event signaled when load goes active.

        Returns:
            The agent's final summary string.
        """
        # Lazy import keeps the agent + models chain out of sys.modules until a
        # fault actually injects; registering the fault only needs the class.
        from devops_bench.chaos.agent import ChaosAgent

        original_url = self.target.service_url
        if local_url is not None:
            self.target.service_url = local_url
        try:
            system_instruction = build_system_instruction(self.target.service_url)
            agent = ChaosAgent(
                system_instruction=system_instruction,
                tool=RUN_COMMAND_TOOL,
                tool_handler=run_chaos_command,
                chaos_active_event=chaos_active_event,
            )
            return agent.run(self.goal())
        finally:
            self.target.service_url = original_url
