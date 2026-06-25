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

Capability wiring is delivered through openclaw's native channels, laid down in
a per-run temp dir:

* **State isolation** — ``OPENCLAW_STATE_DIR`` points at ``<run>/state`` so
  sessions and the skills root live in the per-run dir.
* **MCP servers** — command-bearing bindings become ``mcp.servers`` entries in
  ``<run>/openclaw.json``, selected via ``OPENCLAW_CONFIG_PATH``.
* **Skills** — ``config.capabilities.skills.paths`` are materialized under
  ``<OPENCLAW_STATE_DIR>/skills/<name>/SKILL.md``.
* **Rules** — ``config.capabilities.rules.text`` is prepended to the prompt
  (the ``oc`` build has no dedicated system-prompt flag).
* **Model auth** — ``config.api_key`` is threaded into the provider env var
  (``GEMINI_API_KEY``/``ANTHROPIC_API_KEY``/...) that ``oc agent --local`` reads.

Trajectory extraction uses the official session commands documented in
``docs/openclaw/sessions.md``: run ``oc agent --local``, locate the single
session with ``oc sessions --json``, export it with
``oc sessions export-trajectory``, and parse the bundle. On any extraction miss
the failure is recorded on ``AgentResult.errors`` rather than returning a
silent-empty trajectory.

The bundle parsing lives in :mod:`~devops_bench.agents.cli.openclaw.parsing`.

``__init__`` assigns ``self.rules``, ``self.mcp_servers`` and ``self.skills``
from the granted bindings, so the agent structurally satisfies
``SupportsRules`` / ``SupportsMcp`` / ``SupportsSkills``.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from devops_bench.agents.base import AGENTS, AgentHarness
from devops_bench.agents.cli.openclaw.parsing import (
    _pick_session_key,
    _read_export_bundle,
    _strip_ansi,
    parse_trajectory_export,
)
from devops_bench.agents.config import AgentConfig
from devops_bench.agents.result import AgentResult
from devops_bench.agents.shared.cli_capabilities import (
    build_mcp_servers,
    materialize_skills,
)
from devops_bench.core import SubprocessError, get_logger
from devops_bench.core.subprocess import run

if TYPE_CHECKING:  # pragma: no cover - typing-only import
    from devops_bench.agents.capabilities import McpBinding

__all__ = ["OpenClawAgent"]

_log = get_logger("agents.cli.openclaw.agent")

# Per-run layout under the temp working dir. ``state`` is openclaw's state root
# (sessions + the managed skills tree); ``openclaw.json`` is the isolated config
# carrying ``mcp.servers``.
_OPENCLAW_STATE_DIRNAME = "state"
_OPENCLAW_SKILLS_DIRNAME = "skills"
_OPENCLAW_CONFIG_FILE = "openclaw.json"


def _oc_model_id(config: AgentConfig) -> str:
    """Resolve the canonical ``provider/model`` id ``oc agent --model`` expects.

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


def _build_openclaw_config(mcp_servers: tuple[McpBinding, ...]) -> dict:
    """Assemble the isolated ``openclaw.json`` payload for a run.

    Args:
        mcp_servers: Bindings to render into ``mcp.servers`` (empty-command
            bindings are skipped by :func:`build_mcp_servers`).

    Returns:
        A config mapping with an ``mcp.servers`` section, or an empty dict when
        no binding carries a launch command (caller then skips the config write
        and leaves ``OPENCLAW_CONFIG_PATH`` unset).
    """
    servers = build_mcp_servers(mcp_servers)
    if not servers:
        return {}
    return {"mcp": {"servers": servers}}


def _build_env(config: AgentConfig) -> dict[str, str]:
    """Build the env overlay that gives ``oc agent --local`` its model API key.

    ``oc agent --local`` reads the model provider's API key from the shell. The
    benchmark's neutral ``config.api_key`` is mapped onto the provider-specific
    variable(s) openclaw expects; the model itself is never hardcoded (it flows
    from ``config.model`` via ``oc agent --model``).

    Args:
        config: Resolved :class:`AgentConfig` for this run.

    Returns:
        A mapping suitable for the subprocess environment overlay. The caller
        adds ``OPENCLAW_STATE_DIR`` / ``OPENCLAW_CONFIG_PATH`` on top.
    """
    overlay: dict[str, str] = {}
    if config.api_key:
        provider = (config.provider or "google").strip().lower()
        if provider in ("google", "gemini"):
            overlay["GEMINI_API_KEY"] = config.api_key
            overlay["GOOGLE_API_KEY"] = config.api_key
        elif provider == "anthropic":
            overlay["ANTHROPIC_API_KEY"] = config.api_key
        elif provider == "openai":
            overlay["OPENAI_API_KEY"] = config.api_key
        else:
            overlay["GEMINI_API_KEY"] = config.api_key
    if config.extra_env:
        overlay.update(config.extra_env)
    return overlay


def _oc_model_flag(config: AgentConfig) -> str:
    """Return ``--model <id> `` for ``oc agent``, or ``""`` when no model is set.

    The model is selected per-run with ``oc agent --model`` rather than the
    global ``oc models set``: the latter writes oc's *shared* config whenever no
    isolated ``OPENCLAW_CONFIG_PATH`` is in play (e.g. MCP off), which both races
    across concurrent runs and pollutes the operator's default model. An invalid
    id still aborts the run via ``oc agent``'s own non-zero exit, which surfaces
    on ``AgentResult.errors``.
    """
    model_id = _oc_model_id(config)
    if not model_id:
        return ""
    return f"--model {shlex.quote(model_id)} "


def _prepend_rules(rules_text: str, prompt: str) -> str:
    """Return ``prompt`` with ``rules_text`` prepended as an operator brief.

    Empty / whitespace-only rules pass the prompt through unchanged so a default
    :class:`AgentRules` is indistinguishable from "no preamble". A non-empty
    brief is separated from the prompt by a blank line.

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
    """Build the bash command that sets the model and runs ``oc agent --local``.

    Every interpolated value is ``shlex.quote``d so prompts/agent names
    containing single quotes, spaces, or newlines neither break parsing nor
    inject commands. ``bash -c`` is required so ``nvm.sh`` can be sourced to
    expose the right Node toolchain before invoking ``oc`` (a no-op when Node is
    installed system-wide). Session state is isolated via ``OPENCLAW_STATE_DIR``
    (set by the caller's env overlay).

    Args:
        config: Resolved :class:`AgentConfig`.
        prompt: Task prompt for the agent (rules already prepended).
        agent_name: ``oc`` agent profile (e.g. ``"operator"``).
        oc_bin: Path to the ``oc`` binary.

    Returns:
        A single bash command string ready for ``subprocess.run(shell=True)``.
    """
    quoted_oc = shlex.quote(oc_bin)
    return (
        # Source nvm so the Node-based oc binary's runtime is available.
        'export NVM_DIR="$HOME/.nvm"; '
        '[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; '
        f"{quoted_oc} --log-level debug agent --local "
        f"--agent {shlex.quote(agent_name)} {_oc_model_flag(config)}-m {shlex.quote(prompt)}"
    )


@AGENTS.register("openclaw")
class OpenClawAgent(AgentHarness):
    """OpenClaw CLI agent harness driving the local ``oc`` binary.

    The binary path is resolved from ``config.target``, falling back to
    ``~/bin/oc`` and then ``"oc"`` on ``$PATH``. Model /
    provider flow from ``config.model`` / ``config.provider`` via the per-run
    ``oc agent --model`` flag — never hardcoded, never the global
    ``oc models set``.

    Capabilities are delivered through openclaw's native channels: MCP servers
    via an isolated ``OPENCLAW_CONFIG_PATH`` (``mcp.servers``), skills via
    ``<OPENCLAW_STATE_DIR>/skills``, and rules prepended to the prompt.
    ``__init__`` assigns ``self.rules``, ``self.mcp_servers`` and
    ``self.skills``, so the agent structurally satisfies ``SupportsRules`` /
    ``SupportsMcp`` / ``SupportsSkills``.

    Args:
        config: Typed :class:`AgentConfig`; defaults are used when omitted.
        agent_name: ``oc`` agent profile (defaults to ``"main"``, openclaw's
            built-in default agent, which exists in every config — including the
            per-run isolated one written for MCP).
    """

    def __init__(
        self, config: AgentConfig | None = None, *, agent_name: str = "main"
    ) -> None:
        AgentHarness.__init__(self, config)
        self.agent_name = agent_name
        caps = self.config.capabilities
        self.rules = caps.rules
        self.mcp_servers = caps.mcp_servers
        self.skills = caps.skills

    def _resolve_oc_bin(self) -> str:
        """Pick the ``oc`` binary path from config or fall back."""
        if self.config.target:
            return os.path.expanduser(self.config.target)
        candidate = os.path.expanduser("~/bin/oc")
        return candidate if os.path.exists(candidate) else "oc"

    def _execute(self, prompt: str) -> AgentResult:
        """Run ``oc agent --local`` with the granted capabilities and extract the trajectory.

        The granted capabilities are laid down in a per-run temp dir before
        invocation:

        * ``<run>/state`` — ``OPENCLAW_STATE_DIR`` (sessions + skills root).
        * ``<run>/state/skills/<name>/SKILL.md`` — one per discovered skill.
        * ``<run>/openclaw.json`` — ``mcp.servers`` for each command-bearing MCP
          binding, selected via ``OPENCLAW_CONFIG_PATH``.

        ``rules.text`` is prepended to the prompt; the model API key is threaded
        into the provider env var.
        """
        caps = self.config.capabilities
        oc_bin = self._resolve_oc_bin()
        final_prompt = _prepend_rules(caps.rules.text, prompt)

        with tempfile.TemporaryDirectory(prefix="oc-run-") as rundir:
            workdir = Path(rundir)
            state_dir = workdir / _OPENCLAW_STATE_DIRNAME
            state_dir.mkdir(parents=True, exist_ok=True)

            materialize_skills(state_dir / _OPENCLAW_SKILLS_DIRNAME, caps.skills.paths)

            env_overlay = _build_env(self.config)
            env_overlay["OPENCLAW_STATE_DIR"] = str(state_dir)

            config_payload = _build_openclaw_config(caps.mcp_servers)
            if config_payload:
                config_path = workdir / _OPENCLAW_CONFIG_FILE
                config_path.write_text(json.dumps(config_payload, indent=2))
                env_overlay["OPENCLAW_CONFIG_PATH"] = str(config_path)

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
                    cwd=str(workdir),
                    env={**os.environ, **env_overlay},
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
                errors.append(
                    f"oc agent exited {completed.returncode}: {stderr or '<no stderr>'}"
                )
                metadata["returncode"] = completed.returncode

            trajectory, tokens, bundle_output, export_errors = self._extract_trajectory(
                oc_bin, env_overlay
            )
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
        self, oc_bin: str, env_overlay: dict[str, str]
    ) -> tuple[list[dict], dict, str, list[str]]:
        """Run ``oc sessions`` + ``export-trajectory`` and parse the bundle.

        ``env_overlay`` carries ``OPENCLAW_STATE_DIR`` (and ``OPENCLAW_CONFIG_PATH``
        when MCP is configured) so the session commands read from the same
        isolated state the agent turn wrote to.

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
                extra_env=env_overlay,
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
                    extra_env=env_overlay,
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
