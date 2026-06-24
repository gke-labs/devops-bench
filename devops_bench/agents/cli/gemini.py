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
stream from stdout — no ``~/.gemini/tmp/...`` disk reads, no session-id glob,
no internal-schema parsing. ``tool_use``/``tool_result`` events fold into the
canonical :class:`ToolCall` list; ``result`` events carry the final text and
the aggregated token usage.

Capability wiring is delivered through the Gemini CLI's native workspace
mechanisms, written into the per-run working directory before invocation:

* **Tools** — ``config.capabilities.allowed_tools`` become ``--allowed-tools``
  arguments, pre-approving them in headless mode.
* **MCP servers** — command-bearing bindings become ``mcpServers`` entries in
  ``<cwd>/.gemini/settings.json``.
* **Skills** — ``config.capabilities.skills.paths`` are materialized under
  ``<cwd>/.gemini/skills/<name>/SKILL.md``.
* **Rules** — ``config.capabilities.rules.text`` is written to ``GEMINI.md``,
  auto-loaded as the startup context.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from devops_bench.agents.base import AGENTS, AgentHarness
from devops_bench.agents.config import AgentConfig
from devops_bench.agents.result import AgentResult, ToolCall
from devops_bench.agents.shared.cli_capabilities import (
    build_mcp_servers,
    materialize_skills,
)
from devops_bench.core import SubprocessError, get_logger
from devops_bench.core.subprocess import run

if TYPE_CHECKING:  # pragma: no cover - typing-only import
    from devops_bench.agents.capabilities import McpBinding

__all__ = ["GeminiCliAgent", "parse_stream_json"]

# Filename the Gemini CLI auto-loads from its working directory as the
# operator brief / startup context (its native equivalent of a system prompt).
_GEMINI_RULES_FILE = "GEMINI.md"
# Workspace config dir/files the CLI reads from its cwd. ``settings.json`` here
# overrides the user-level ``~/.gemini/settings.json``; ``skills/`` is the
# workspace skill-discovery root.
_GEMINI_CONFIG_DIR = ".gemini"
_GEMINI_SETTINGS_FILE = "settings.json"
_GEMINI_SKILLS_DIR = "skills"

_log = get_logger("agents.cli.gemini")


def _build_settings(mcp_servers: tuple[McpBinding, ...], *, skills_enabled: bool) -> dict:
    """Assemble the Gemini ``settings.json`` payload for a run.

    Args:
        mcp_servers: Bindings to render into ``mcpServers`` (empty-command
            bindings are skipped by :func:`build_mcp_servers`).
        skills_enabled: Whether any workspace skill was materialized; gates the
            explicit ``skills.enabled`` flag so the benchmark does not depend on
            the user-level default.

    Returns:
        A settings mapping, possibly empty (caller skips the write when empty).
    """
    settings: dict = {}
    servers = build_mcp_servers(mcp_servers)
    if servers:
        settings["mcpServers"] = servers
    if skills_enabled:
        settings["skills"] = {"enabled": True}
    return settings


def _build_argv(target: str, prompt: str, allowed_tools: tuple[str, ...]) -> list[str]:
    """Build the ``gemini`` invocation for ``prompt``.

    When ``allowed_tools`` is empty, extensions are disabled via
    ``--extensions=`` — the headless "no tools" arm. The short ``-e=`` / ``-e=""``
    forms print help and exit non-zero on gemini >= 0.47 (the literal value,
    quotes included, reaches the parser since argv bypasses the shell), and
    ``-e none`` loads an extension literally named "none" rather than disabling.

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
        # `--extensions=` disables extensions; `-e=`/`-e=""` print help + exit 1
        # on gemini >= 0.47, and `-e none` loads an extension named "none".
        argv.append("--extensions=")
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


def parse_stream_json(stdout: str) -> tuple[str, list[dict], dict, list[str]]:
    """Parse a Gemini ``--output-format stream-json`` stdout stream.

    The stream is newline-delimited JSON events. The parser is intentionally
    lenient (an unknown event type is skipped) and surfaces both per-line JSON
    decode errors and unmatched ``tool_result`` events on the ``errors`` list
    rather than silently dropping them.

    | Event type      | Fields read                                              |
    |-----------------|---------------------------------------------------------|
    | ``init``        | (ignored)                                               |
    | ``message``     | ``role`` (assistant text accumulated into the output)   |
    | ``tool_use``    | ``tool_name``, ``tool_id``, ``parameters``              |
    | ``tool_result`` | ``tool_id``, ``status`` (no payload in the stream)      |
    | ``error``       | recorded on the errors list                             |
    | ``result``      | ``stats`` (token usage); terminal status                |

    Args:
        stdout: Raw process stdout, possibly empty.

    Returns:
        A ``(output, trajectory, tokens, errors)`` tuple. ``trajectory`` is a
        list of ``ToolCall.to_dict()`` mappings ordered as emitted.
    """
    output_parts: list[str] = []
    tokens: dict = {}
    errors: list[str] = []
    pending: dict[str, ToolCall] = {}
    trajectory: list[ToolCall] = []

    for lineno, raw in enumerate(stdout.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"stream-json line {lineno} parse error: {exc}")
            continue
        if not isinstance(event, dict):
            continue

        etype = event.get("type")
        if etype == "message":
            # ``role="user"`` echoes the prompt and is skipped.
            if event.get("role") in ("assistant", "model"):
                content = event.get("content")
                if isinstance(content, str):
                    output_parts.append(content)
                elif isinstance(content, list):
                    # Defensive: a parts-list shape (``[{"text": ...}]``).
                    for part in content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            output_parts.append(part["text"])
        elif etype == "tool_use":
            call_id = event.get("tool_id") or event.get("id") or event.get("tool_use_id") or ""
            args = event.get("parameters")
            if args is None:
                args = event.get("input")
            if args is None:
                args = event.get("args")
            call = ToolCall(
                name=event.get("tool_name") or event.get("name", ""),
                args=args if isinstance(args, dict) else {},
                status="called",
            )
            trajectory.append(call)
            if call_id:
                pending[str(call_id)] = call
        elif etype == "tool_result":
            call_id = event.get("tool_id") or event.get("tool_use_id") or event.get("id") or ""
            target = pending.pop(str(call_id), None) if call_id else None
            if target is None:
                errors.append(f"stream-json tool_result without matching tool_use (id={call_id!r})")
                continue
            # tool_result carries only a status; accept a content/output
            # payload as a fallback when present.
            content = event.get("content")
            if content is None:
                content = event.get("output")
            if content is not None:
                target.result = content if isinstance(content, str) else json.dumps(content, default=str)
            status = str(event.get("status", "")).lower()
            failed = bool(event.get("is_error")) or status in ("error", "failed", "failure")
            target.status = "error" if failed else "completed"
        elif etype == "error":
            msg = event.get("message") or event.get("error") or str(event)
            errors.append(f"stream-json error event: {msg}")
        elif etype == "result":
            # Terminal event: answer streams via ``message`` events and token
            # usage rides under ``stats``; accept ``output``/``response`` and
            # ``tokens``/``usage`` as fallbacks.
            tail = event.get("output") or event.get("response")
            if isinstance(tail, str) and tail:
                output_parts.append(tail)
            stats = event.get("stats")
            usage = event.get("tokens") or event.get("usage")
            if isinstance(stats, dict):
                tokens = {
                    "input": stats.get("input_tokens"),
                    "output": stats.get("output_tokens"),
                    "total": stats.get("total_tokens"),
                    "cached": stats.get("cached"),
                }
            elif isinstance(usage, dict):
                tokens = usage

    return "".join(output_parts), [call.to_dict() for call in trajectory], tokens, errors


@AGENTS.register("gemini")
class GeminiCliAgent(AgentHarness):
    """Gemini CLI agent harness driving the ``gemini`` binary.

    The binary path is resolved from ``config.target``, falling back to
    ``"gemini"`` on ``$PATH``. Model / API key flow from
    ``config.model`` / ``config.api_key`` via the env overlay — never
    hardcoded. ``config.capabilities.allowed_tools`` (aggregated across every
    bound MCP server) selects between the ``--allowed-tools`` overlay and the
    ``--extensions=`` extensions-disabled path.

    ``__init__`` assigns ``self.mcp_servers``, ``self.skills`` and ``self.rules``
    from the granted config bindings, which is what makes
    ``isinstance(agent, SupportsMcp / SupportsSkills / SupportsRules)`` return
    ``True`` for orchestrator-side capability negotiation (the Protocols are
    structural).

    The full canonical trajectory is parsed from the official
    ``--output-format stream-json`` event stream; no session files are read
    from disk.
    """

    def __init__(self, config: AgentConfig | None = None) -> None:
        AgentHarness.__init__(self, config)
        caps = self.config.capabilities
        self.mcp_servers = caps.mcp_servers
        self.skills = caps.skills
        self.rules = caps.rules

    def _execute(self, prompt: str) -> AgentResult:
        """Build argv, run the CLI, and parse the stream-json output.

        The agent always runs the binary inside a per-run temp working
        directory and lays down the granted capabilities there before
        invocation, using the CLI's native workspace channels (all auto-loaded
        from the cwd, so the user's ``~/.gemini`` stays untouched and concurrent
        runs never race):

        * ``GEMINI.md`` — the operator brief, when ``rules.text`` is set.
        * ``.gemini/settings.json`` — ``mcpServers`` for each command-bearing
          MCP binding, plus ``skills.enabled`` when skills were materialized.
        * ``.gemini/skills/<name>/SKILL.md`` — one per discovered skill.

        The temp dir is cleaned up when ``_execute`` returns.
        """
        caps = self.config.capabilities
        target = os.path.expanduser(self.config.target or "gemini")
        argv = _build_argv(target, prompt, caps.allowed_tools)
        env_overlay = _build_env(self.config)
        rules_text = caps.rules.text

        with tempfile.TemporaryDirectory(prefix="gemini-run-") as tmpdir:
            workdir = Path(tmpdir)
            if rules_text:
                (workdir / _GEMINI_RULES_FILE).write_text(
                    rules_text, encoding="utf-8"
                )

            gemini_dir = workdir / _GEMINI_CONFIG_DIR
            skill_names = materialize_skills(
                gemini_dir / _GEMINI_SKILLS_DIR, caps.skills.paths
            )
            settings = _build_settings(caps.mcp_servers, skills_enabled=bool(skill_names))
            if settings:
                gemini_dir.mkdir(parents=True, exist_ok=True)
                (gemini_dir / _GEMINI_SETTINGS_FILE).write_text(
                    json.dumps(settings, indent=2), encoding="utf-8"
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
