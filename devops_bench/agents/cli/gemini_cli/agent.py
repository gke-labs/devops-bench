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

"""Gemini CLI agent harness driving the ``gemini`` binary.

Trajectory extraction reads the official ``--output-format stream-json`` event
stream from stdout (see :mod:`~devops_bench.agents.cli.gemini_cli.parsing`) — no
``~/.gemini/tmp/...`` disk reads, no session-id glob, no internal-schema parsing.

Capability wiring: the allowed-tools list comes from the aggregated
``config.capabilities.allowed_tools`` (across every bound MCP server) and the
operator brief from ``config.capabilities.rules.text`` (written to a
``GEMINI.md`` file in the run working directory before invocation, the CLI's
native context-file mechanism).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from devops_bench.agents.base import AGENTS, AgentHarness
from devops_bench.agents.cli.gemini_cli.parsing import parse_stream_json
from devops_bench.agents.config import AgentConfig
from devops_bench.agents.result import AgentResult
from devops_bench.core import SubprocessError, get_logger
from devops_bench.core.subprocess import run

__all__ = ["GeminiCliAgent"]

# Filename the Gemini CLI auto-loads from its working directory as the
# operator brief / startup context (its native equivalent of a system prompt).
_GEMINI_RULES_FILE = "GEMINI.md"

_log = get_logger("agents.cli.gemini_cli")


def _build_argv(target: str, prompt: str, allowed_tools: tuple[str, ...]) -> list[str]:
    """Build the ``gemini`` invocation for ``prompt``.

    When ``allowed_tools`` is empty, extensions are disabled via ``-e=""`` —
    the documented switch for the headless "no tools" arm; ``-e none`` does
    *not* disable extensions despite reading like it should.

    Args:
        target: Path to the ``gemini`` binary (already user-expanded).
        prompt: Task prompt.
        allowed_tools: Pre-approved tool names; each yields a separate
            ``--allowed-tools <name>`` pair so the CLI never blocks on
            interactive confirmation in headless mode.

    Returns:
        The argv list ready to hand to ``core.subprocess.run``.
    """
    argv = [target, "--output-format", "stream-json", "--skip-trust"]
    if allowed_tools:
        for tool in allowed_tools:
            argv.extend(["--allowed-tools", tool])
    else:
        # `-e=""` disables extensions; `-e none` does not (it loads the
        # extension literally named "none" and silently no-ops).
        argv.append('-e=""')
    argv.extend(["-p", prompt])
    return argv


def _build_env(config: AgentConfig) -> dict[str, str]:
    """Build the env overlay that makes the Gemini CLI run model-agnostic.

    Maps the benchmark's neutral ``AGENT_*`` fields onto the variables the
    Gemini CLI expects (``GOOGLE_API_KEY``/``GEMINI_API_KEY``/``GEMINI_MODEL``)
    and disables OTLP telemetry exporters that otherwise hang on broken
    endpoints. The model is never hardcoded; it flows from ``config.model``.

    Args:
        config: Resolved :class:`AgentConfig` for this run.

    Returns:
        A mapping suitable for ``core.subprocess.run``'s ``extra_env``.
    """
    overlay: dict[str, str] = {
        # Disable the Gemini CLI's OTLP exporters; otherwise they block/hang
        # trying to reach an unreachable collector endpoint in headless runs.
        "OTEL_TRACES_EXPORTER": "none",
        "OTEL_METRICS_EXPORTER": "none",
        "OTEL_LOGS_EXPORTER": "none",
        "OTEL_SDK_DISABLED": "true",
    }
    if config.api_key:
        overlay["GOOGLE_API_KEY"] = config.api_key
        overlay["GEMINI_API_KEY"] = config.api_key
    if config.model:
        overlay["GEMINI_MODEL"] = config.model
    if config.extra_env:
        overlay.update(config.extra_env)
    return overlay


@AGENTS.register("gemini")
class GeminiCliAgent(AgentHarness):
    """Gemini CLI agent harness driving the ``gemini`` binary.

    The binary path is resolved from ``config.target``, falling back to
    ``"gemini"`` on ``$PATH``. Model / API key flow from
    ``config.model`` / ``config.api_key`` via the env overlay — never
    hardcoded. ``config.capabilities.allowed_tools`` (aggregated across every
    bound MCP server) selects between the ``--allowed-tools`` overlay and the
    ``-e=""`` extensions-disabled path.

    ``__init__`` assigns ``self.mcp_servers`` and ``self.rules`` from the
    granted config bindings, which is what makes
    ``isinstance(agent, SupportsMcp / SupportsRules)`` return ``True`` for
    orchestrator-side capability negotiation (the Protocols are structural).

    The full canonical trajectory is parsed from the official
    ``--output-format stream-json`` event stream; no session files are read
    from disk.
    """

    def __init__(self, config: AgentConfig | None = None) -> None:
        AgentHarness.__init__(self, config)
        caps = self.config.capabilities
        self.mcp_servers = caps.mcp_servers
        self.rules = caps.rules

    def _execute(self, prompt: str) -> AgentResult:
        """Build argv, run the CLI, and parse the stream-json output.

        When ``capabilities.rules.text`` is non-empty, the agent runs the
        binary inside a per-run temp working directory and writes the rules
        text to ``GEMINI.md`` there before invocation — the CLI auto-loads
        that file as its startup context, which is the binary's native
        delivery mechanism for an operator brief. The temp dir is cleaned up
        when ``_execute`` returns.
        """
        target = os.path.expanduser(self.config.target or "gemini")
        allowed_tools = self.config.capabilities.allowed_tools
        argv = _build_argv(target, prompt, allowed_tools)
        env_overlay = _build_env(self.config)
        rules_text = self.config.capabilities.rules.text

        with tempfile.TemporaryDirectory(prefix="gemini-run-") as tmpdir:
            if rules_text:
                (Path(tmpdir) / _GEMINI_RULES_FILE).write_text(
                    rules_text, encoding="utf-8"
                )
            try:
                completed = run(
                    argv,
                    extra_env=env_overlay,
                    cwd=tmpdir,
                    check=False,
                    timeout=self.config.timeout_sec,
                )
            except SubprocessError as exc:
                return AgentResult.errored(f"gemini subprocess error: {exc}")
            except OSError as exc:
                # Missing / non-executable binary; core.subprocess.run does not wrap.
                return AgentResult.errored(f"gemini binary unavailable: {exc}")

        output, trajectory, tokens, parse_errors = parse_stream_json(completed.stdout or "")
        errors: list[str] = list(parse_errors)
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            errors.append(f"gemini exited {completed.returncode}: {stderr or '<no stderr>'}")
            if not output:
                output = f"Error: gemini exited {completed.returncode}"
        metadata: dict = {}
        if completed.returncode != 0:
            metadata["returncode"] = completed.returncode
        return AgentResult(
            output=output,
            trajectory=trajectory,
            tokens=tokens,
            errors=errors,
            metadata=metadata,
        )
