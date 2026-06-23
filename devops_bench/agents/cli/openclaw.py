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
5. Parse the bundle's ``events.jsonl`` (dotted-``type`` events with a nested
   ``data`` payload) into canonical :class:`ToolCall` entries, and pull the
   final answer + token usage from its ``model.completed`` event.

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

import json
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

from devops_bench.agents.base import AGENTS, AgentHarness
from devops_bench.agents.config import AgentConfig
from devops_bench.agents.result import AgentResult, ToolCall
from devops_bench.core import SubprocessError, get_logger
from devops_bench.core.subprocess import run

__all__ = ["OpenClawAgent", "parse_trajectory_export"]

_log = get_logger("agents.cli.openclaw")

# OpenClaw emits ANSI-colored debug logs to stdout. The escape codes add noise
# to the text the judge grades, so strip them before returning the output.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


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


def _join_text(content: object) -> str:
    """Join the ``text`` parts of an OpenClaw message ``content`` value.

    ``content`` is either a plain string or a list of typed parts
    (``{"type": "text", "text": ...}`` / ``{"type": "toolCall", ...}``); only
    text parts contribute, so tool-call blocks embedded in an assistant message
    are ignored here (they ride on the dedicated ``tool.call`` events instead).
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part["text"]
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    return ""


def parse_trajectory_export(jsonl_text: str) -> tuple[list[dict], dict, str, list[str]]:
    """Parse an ``oc sessions export-trajectory`` ``events.jsonl`` into the canonical shape.

    The export bundle's ``events.jsonl`` is line-delimited JSON. Each line is an
    event with a dotted ``type`` and an event-specific ``data`` payload:

    - ``tool.call`` -> ``data.name`` / ``data.arguments`` / ``data.toolCallId``
    - ``tool.result`` -> ``data.message`` with ``toolCallId`` + ``content[].text``
      (+ ``isError`` / ``details.status``)
    - ``model.completed`` -> ``data.usage`` (tokens) + ``data.assistantTexts``
      (the agent's final answer)
    - ``assistant.message`` -> ``data.message.content[].text`` (fallback output)

    Matching ``tool.call`` / ``tool.result`` pairs (keyed on ``toolCallId``) fold
    into one :class:`ToolCall` so the metrics layer sees the canonical trajectory
    other agents emit. An unpaired ``tool.result`` (no matching call seen) is
    **dropped** from the trajectory and reported on ``errors``, matching the API
    agent's ``_fold_with_extraction_errors`` and the Gemini ``parse_stream_json``
    policy.

    Args:
        jsonl_text: Raw contents of ``events.jsonl`` inside the export bundle.

    Returns:
        A ``(trajectory, tokens, output, errors)`` tuple. ``trajectory`` is a
        list of ``ToolCall.to_dict()`` mappings; ``output`` is the agent's final
        answer text (``""`` when none was found).
    """
    tokens: dict = {}
    errors: list[str] = []
    output = ""
    fallback_output: list[str] = []
    pending: dict[str, ToolCall] = {}
    trajectory: list[ToolCall] = []

    for lineno, raw in enumerate(jsonl_text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"events line {lineno} parse error: {exc}")
            continue
        if not isinstance(entry, dict):
            continue

        etype = entry.get("type") or entry.get("event")
        data = entry.get("data")
        if not isinstance(data, dict):
            data = {}

        if etype == "tool.call":
            call_id = data.get("toolCallId") or data.get("id") or ""
            args = data.get("arguments")
            call = ToolCall(
                name=data.get("name", ""),
                args=args if isinstance(args, dict) else {},
                status="called",
            )
            trajectory.append(call)
            if call_id:
                pending[str(call_id)] = call
        elif etype == "tool.result":
            msg = data.get("message") if isinstance(data.get("message"), dict) else data
            call_id = msg.get("toolCallId") or msg.get("id") or ""
            text = _join_text(msg.get("content"))
            details = msg.get("details") if isinstance(msg.get("details"), dict) else {}
            is_error = bool(msg.get("isError")) or (
                str(details.get("status", "")).lower() in ("error", "failed", "failure")
            )
            target = pending.pop(str(call_id), None) if call_id else None
            if target is None:
                # Drop the orphan from the trajectory but surface it on errors.
                # Synthesizing a free-floating result entry would break the
                # "every trajectory item is a real ToolCall the model issued"
                # invariant the metrics layer relies on; the API agent's
                # ``_fold_with_extraction_errors`` and the Gemini stream-json
                # parser both apply the same rule, so every agent feeds the
                # metrics seam an identical canonical shape.
                preview = text[:80].replace("\n", " ")
                errors.append(
                    f"events tool.result without matching call "
                    f"(id={call_id!r}, content={preview!r})"
                )
                continue
            target.result = text
            target.status = "error" if is_error else "completed"
        elif etype == "model.completed":
            usage = data.get("usage")
            if isinstance(usage, dict):
                tokens = usage
            texts = data.get("assistantTexts")
            if isinstance(texts, list):
                joined = "\n".join(t for t in texts if isinstance(t, str))
                if joined:
                    output = joined
        elif etype == "assistant.message":
            msg = data.get("message") if isinstance(data.get("message"), dict) else {}
            txt = _join_text(msg.get("content"))
            if txt:
                fallback_output.append(txt)

    if not output and fallback_output:
        output = "\n".join(fallback_output)

    return [call.to_dict() for call in trajectory], tokens, output, errors


def _read_export_bundle(workspace: Path) -> tuple[str, list[str]]:
    """Locate and read ``events.jsonl`` inside an ``export-trajectory`` bundle.

    The bundle is written under
    ``<workspace>/.openclaw/trajectory-exports/openclaw-trajectory-<id>-<ts>/``;
    the trajectory itself is ``events.jsonl`` (siblings: ``manifest.json``,
    ``tools.json``, ``metadata.json``, ...). There is exactly one export per run,
    so a recursive glob suffices. The final answer + token usage are parsed out
    of ``events.jsonl`` (``model.completed`` / ``assistant.message``), so no
    separate output file is read.

    Args:
        workspace: Workspace dir handed to ``oc sessions export-trajectory --workspace``.

    Returns:
        A ``(events_jsonl, errors)`` tuple. ``events_jsonl`` is empty when the
        bundle or file is missing; the miss is recorded on ``errors``.
    """
    errors: list[str] = []
    export_root = workspace / ".openclaw" / "trajectory-exports"
    if not export_root.exists():
        errors.append(f"export-trajectory bundle missing: {export_root}")
        return "", errors

    event_files = sorted(export_root.rglob("events.jsonl"))
    if not event_files:
        errors.append(f"no events.jsonl under {export_root}")
        return "", errors
    try:
        return event_files[0].read_text(encoding="utf-8"), errors
    except OSError as exc:
        errors.append(f"failed to read {event_files[0]}: {exc}")
        return "", errors


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


def _pick_session_key(sessions_json: str) -> str | None:
    """Return the single session key from ``oc sessions --json`` output, or ``None``.

    The output may be a list of rows or a wrapper dict with a ``sessions``
    list (per ``docs/openclaw/sessions.md``). Because the run wiped the
    sessions dir first, exactly one row is expected; if more than one is
    present the first is taken (with a debug log).

    Args:
        sessions_json: Raw stdout from ``oc sessions --agent <name> --json``.

    Returns:
        The ``key`` field of the chosen session, or ``None`` if parsing
        failed or no sessions were returned.
    """
    try:
        data = json.loads(sessions_json)
    except json.JSONDecodeError:
        return None
    rows = data.get("sessions") if isinstance(data, dict) else data
    if not isinstance(rows, list) or not rows:
        return None
    if len(rows) > 1:
        _log.debug("oc sessions returned %d rows; using the first", len(rows))
    first = rows[0]
    if not isinstance(first, dict):
        return None
    key = first.get("key")
    return key if isinstance(key, str) and key else None
