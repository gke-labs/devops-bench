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

"""OpenClaw CLI agent harness driving the ``oc`` binary (local-only).

Trajectory extraction uses the official session commands documented in
``docs/openclaw/sessions.md`` — *not* the debug-log ``sessionFile=`` scrape,
and *not* ``sessions tail`` (which redacts tool args / result bodies):

1. Wipe ``~/.openclaw/agents/<name>/sessions/*`` before the run so exactly
   one fresh session exists afterward.
2. Run ``oc agent --local --agent <name> -m <prompt>``.
3. Locate the session: ``oc sessions --agent <name> --json`` (single row).
4. Export the bundle: ``oc sessions export-trajectory --session-key <key>
   --workspace <tmpdir> --json``.
5. Parse the bundle (see :mod:`~devops_bench.agents.cli.openclaw.parsing`) into
   canonical :class:`ToolCall` entries plus the final answer and token usage.

The ``oc`` binary is a custom alias on the user's host; on any extraction
miss the failure is recorded on ``AgentResult.errors`` rather than returning
a silent-empty trajectory.

Capability wiring: ``capabilities.rules.text`` is **prepended to the prompt**
(separated by a blank line) before invocation. The installed ``oc`` build has
no dedicated rules / system-prompt flag, so prompt-prepending is the reliable,
binary-agnostic delivery channel. The agent assigns only ``self.rules`` in
``__init__`` (satisfying :class:`SupportsRules`) and leaves ``mcp_servers`` /
``skills`` unset — granting MCP or skills bindings would silently no-op against
the ``oc`` build.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from devops_bench.agents.base import AGENTS, AgentHarness
from devops_bench.agents.cli.openclaw.parsing import (
    _pick_session_key,
    _read_export_bundle,
    _strip_ansi,
    parse_trajectory_export,
)
from devops_bench.agents.config import AgentConfig
from devops_bench.agents.result import AgentResult
from devops_bench.core import SubprocessError, get_logger
from devops_bench.core.subprocess import run

__all__ = ["OpenClawAgent"]

_log = get_logger("agents.cli.openclaw.agent")


def _oc_model_id(config: AgentConfig) -> str:
    """Resolve the canonical ``provider/model`` id ``oc models set`` expects.

    Returns ``""`` when no model is configured (oc's stored default is left
    untouched). A model id already containing ``/`` passes through; otherwise
    ``config.provider`` is prefixed (defaulting to ``google``, with ``gemini``
    normalized to ``google``).

    >>> _oc_model_id(AgentConfig(model="gemini-2.5-pro", provider="gemini"))
    'google/gemini-2.5-pro'
    >>> _oc_model_id(AgentConfig(model="anthropic/claude-opus-4"))
    'anthropic/claude-opus-4'
    >>> _oc_model_id(AgentConfig(model="gpt-5", provider="openai"))
    'openai/gpt-5'
    >>> _oc_model_id(AgentConfig())
    ''
    """
    model = (config.model or "").strip()
    if not model:
        return ""
    if "/" in model:  # already a full oc id
        return model
    provider = (config.provider or "google").strip().lower()
    if provider == "gemini":
        provider = "google"
    return f"{provider}/{model}"


def _prepend_rules(rules_text: str, prompt: str) -> str:
    """Return ``prompt`` with ``rules_text`` prepended as an operator brief.

    Empty / whitespace-only rules pass the prompt through unchanged so a
    default :class:`AgentRules` is indistinguishable from "no preamble". A
    non-empty brief is separated from the prompt by a blank line so the
    model sees two distinct sections.

    Args:
        rules_text: The bound rules text (``capabilities.rules.text``).
        prompt: The task prompt for this run.

    Returns:
        The combined string to hand to ``oc agent -m``.
    """
    if not rules_text or not rules_text.strip():
        return prompt
    return f"{rules_text.rstrip()}\n\n{prompt}"


def _build_local_command(
    config: AgentConfig, prompt: str, agent_name: str, oc_bin: str
) -> str:
    """Build the bash command that wipes sessions, sets the model, and runs ``oc``.

    Every interpolated value is ``shlex.quote``d so prompts/agent names
    containing single quotes, spaces, or newlines neither break parsing nor
    inject commands. ``bash -c`` is required so ``nvm.sh`` can be sourced to
    expose the right Node toolchain before invoking ``oc``.

    Args:
        config: Resolved :class:`AgentConfig`.
        prompt: Task prompt for the agent.
        agent_name: ``oc`` agent profile (e.g. ``"operator"``).
        oc_bin: Path to the ``oc`` binary.

    Returns:
        A single bash command string ready for ``subprocess.run(shell=True)``.
    """
    quoted_oc = shlex.quote(oc_bin)
    sessions_dir = os.path.expanduser(f"~/.openclaw/agents/{agent_name}/sessions")
    model_id = _oc_model_id(config)
    # Chain `models set` with `&&` so a failed model-set aborts the run; the
    # bash non-zero exit then surfaces via `completed.returncode` and lands on
    # `AgentResult.errors` rather than silently falling through to oc's stored
    # default (which would invalidate the benchmark arm).
    set_model = (
        f"{quoted_oc} models set {shlex.quote(model_id)} && " if model_id else ""
    )
    return (
        # Wipe prior sessions so exactly one fresh session exists afterward.
        f"rm -rf {shlex.quote(sessions_dir)}/* 2>/dev/null; "
        # Source nvm so the Node-based oc binary's runtime is available.
        'export NVM_DIR="$HOME/.nvm"; '
        '[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; '
        f"{set_model}"
        f"{quoted_oc} --log-level debug agent --local "
        f"--agent {shlex.quote(agent_name)} -m {shlex.quote(prompt)}"
    )


@AGENTS.register("openclaw")
class OpenClawAgent(AgentHarness):
    """OpenClaw CLI agent harness driving the local ``oc`` binary.

    The binary path is resolved from ``config.target``, falling back to
    ``~/bin/oc`` and then ``"oc"`` on ``$PATH``. Model /
    provider flow from ``config.model`` / ``config.provider`` via an
    ``oc models set <id>`` fragment prepended to the bash command — never
    hardcoded. Trajectory is exported through the official
    ``oc sessions export-trajectory`` command into a per-run temp workspace
    and parsed into the canonical :class:`ToolCall` list.

    ``__init__`` assigns ``self.rules`` (satisfying :class:`SupportsRules`) so
    the orchestrator can grant operator-brief text uniformly. The installed
    ``oc`` build exposes no in-agent MCP or skills wiring, so
    ``mcp_servers`` / ``skills`` are deliberately *not* assigned —
    ``isinstance(agent, SupportsMcp / SupportsSkills)`` stays ``False`` rather
    than granting a binding the agent silently ignores.

    Args:
        config: Typed :class:`AgentConfig`; defaults are used when omitted.
        agent_name: ``oc`` agent profile (defaults to ``"operator"``).
    """

    def __init__(
        self, config: AgentConfig | None = None, *, agent_name: str = "operator"
    ) -> None:
        AgentHarness.__init__(self, config)
        self.agent_name = agent_name
        self.rules = self.config.capabilities.rules

    def _resolve_oc_bin(self) -> str:
        """Pick the ``oc`` binary path from config or fall back."""
        if self.config.target:
            return os.path.expanduser(self.config.target)
        candidate = os.path.expanduser("~/bin/oc")
        return candidate if os.path.exists(candidate) else "oc"

    def _execute(self, prompt: str) -> AgentResult:
        """Run ``oc agent --local`` and extract the canonical trajectory.

        When ``capabilities.rules.text`` is non-empty, the rules are
        **prepended to the prompt** (separated by a blank line) before being
        passed to ``oc agent -m`` — the ``oc`` build exposes no dedicated rules
        / system-prompt flag.
        """
        oc_bin = self._resolve_oc_bin()
        final_prompt = _prepend_rules(self.config.capabilities.rules.text, prompt)
        command = _build_local_command(self.config, final_prompt, self.agent_name, oc_bin)

        try:
            completed = subprocess.run(
                command,
                shell=True,  # noqa: S602 - bash needed for nvm; all values shlex.quoted
                executable="/bin/bash",
                capture_output=True,
                text=True,
                check=False,
                timeout=self.config.timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            return AgentResult.errored(f"oc agent timed out after {exc.timeout}s")
        except OSError as exc:
            return AgentResult.errored(f"oc binary unavailable: {exc}")

        stdout_text = _strip_ansi(completed.stdout or "")
        errors: list[str] = []
        metadata: dict = {}

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            errors.append(f"oc agent exited {completed.returncode}: {stderr or '<no stderr>'}")
            metadata["returncode"] = completed.returncode

        trajectory, tokens, bundle_output, export_errors = self._extract_trajectory(oc_bin)
        errors.extend(export_errors)

        # Bundle text is clean; bash stdout carries debug noise — fall back only if empty.
        output = bundle_output if bundle_output else stdout_text

        return AgentResult(
            output=output,
            trajectory=trajectory,
            tokens=tokens,
            errors=errors,
            metadata=metadata,
        )

    def _extract_trajectory(
        self, oc_bin: str
    ) -> tuple[list[dict], dict, str, list[str]]:
        """Run ``oc sessions`` + ``export-trajectory`` and parse the bundle.

        Returns:
            A ``(trajectory, tokens, output_text, errors)`` tuple. ``output_text``
            is the agent's final answer parsed from the bundle's ``events.jsonl``
            (``model.completed.assistantTexts``) when present, else ``""``; the
            caller falls back to the ansi-stripped subprocess stdout when empty.
        """
        errors: list[str] = []
        try:
            sessions = run(
                [oc_bin, "sessions", "--agent", self.agent_name, "--json"],
                check=False,
                timeout=self.config.timeout_sec,
            )
        except SubprocessError as exc:
            errors.append(f"oc sessions failed: {exc}")
            return [], {}, "", errors
        except OSError as exc:
            errors.append(f"oc sessions: binary unavailable: {exc}")
            return [], {}, "", errors

        if sessions.returncode != 0:
            stderr = (sessions.stderr or "").strip()
            errors.append(
                f"oc sessions exited {sessions.returncode}: {stderr or '<no stderr>'}"
            )
            return [], {}, "", errors

        key = _pick_session_key(sessions.stdout or "")
        if key is None:
            errors.append("oc sessions returned no session key")
            return [], {}, "", errors

        with tempfile.TemporaryDirectory(prefix="oc-export-") as tmpdir:
            workspace = Path(tmpdir)
            try:
                export = run(
                    [
                        oc_bin,
                        "sessions",
                        "export-trajectory",
                        "--session-key",
                        key,
                        "--workspace",
                        str(workspace),
                        "--json",
                    ],
                    check=False,
                    timeout=self.config.timeout_sec,
                )
            except SubprocessError as exc:
                errors.append(f"oc export-trajectory failed: {exc}")
                return [], {}, "", errors
            except OSError as exc:
                errors.append(f"oc export-trajectory: binary unavailable: {exc}")
                return [], {}, "", errors

            if export.returncode != 0:
                stderr = (export.stderr or "").strip()
                errors.append(
                    f"oc export-trajectory exited {export.returncode}: "
                    f"{stderr or '<no stderr>'}"
                )
                return [], {}, "", errors

            events_text, read_errors = _read_export_bundle(workspace)
            errors.extend(read_errors)
            if not events_text:
                return [], {}, "", errors

            trajectory, tokens, output_text, parse_errors = parse_trajectory_export(
                events_text
            )
            errors.extend(parse_errors)
            return trajectory, tokens, output_text, errors
