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

"""Claude Code CLI agent harness driving the ``claude`` binary.

Runs ``claude`` in headless mode (``-p --output-format stream-json --verbose``)
and extracts the canonical trajectory from the official event stream on stdout
(see :mod:`~devops_bench.agents.cli.claude_code.parsing`) — no session-file
reads off disk.

Capability wiring uses Claude Code's native cwd-based channels, written into the
per-run working directory before invocation:

* **Rules** — ``config.capabilities.rules.text`` → ``CLAUDE.md``, auto-loaded
  from the cwd as the startup context.
* **Skills** — ``config.capabilities.skills.paths`` are materialized under
  ``<cwd>/.claude/skills/<name>/SKILL.md``, Claude Code's skill-discovery root.
* **MCP servers** — command-bearing bindings become a ``{"mcpServers": ...}``
  document at ``<cwd>/.claude/mcp-config.json``, passed via ``--mcp-config``
  together with ``--strict-mcp-config`` so any stray project ``.mcp.json`` is
  ignored and no trust prompt fires.

Auth is env-driven, matching the bench contract: ``config.api_key`` →
``ANTHROPIC_API_KEY`` for the direct API, or keyless Vertex / Bedrock whose ADC
/ AWS credentials live outside the config dir. ``CLAUDE_CONFIG_DIR`` is
redirected to a fresh per-run temp dir so Claude Code's mutable global state
(config, sessions, trust) never races across concurrent evals — which means a
cached subscription OAuth login in ``~/.claude`` is not visible. For OAuth-based
local debugging, export ``CLAUDE_CONFIG_DIR=~/.claude`` yourself: an ambient
value is respected and the per-run temp dir is not injected.

For keyless Vertex under ``--parallel`` locally, note that ``RunEnv.apply()``
redirects ``CLOUDSDK_CONFIG`` to a per-run dir, so google-auth cannot find user
ADC via that path; export ``GOOGLE_APPLICATION_CREDENTIALS`` at the real ADC
file to bypass the lookup. On the bastion, metadata-server ADC needs no file and
this is a non-issue.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

from devops_bench.agents.base import AGENTS, AgentHarness
from devops_bench.agents.cli.claude_code.parsing import parse_stream_json
from devops_bench.agents.config import AgentConfig
from devops_bench.agents.result import AgentResult
from devops_bench.agents.shared.cli_capabilities import (
    agent_workdir,
    build_mcp_servers,
    materialize_skills,
)
from devops_bench.core import SubprocessError, get_logger
from devops_bench.core.model_providers import resolve_provider
from devops_bench.core.subprocess import run

__all__ = ["ClaudeCodeAgent"]

# Filename Claude Code auto-loads from its working directory as the operator
# brief / startup context (its native equivalent of a system prompt).
_CLAUDE_RULES_FILE = "CLAUDE.md"
# Workspace config dir/files Claude Code reads from its cwd: ``skills/`` is the
# skill-discovery root and ``mcp-config.json`` is passed via ``--mcp-config``.
_CLAUDE_CONFIG_DIRNAME = ".claude"
_CLAUDE_SKILLS_DIR = "skills"
_CLAUDE_MCP_FILE = "mcp-config.json"
# Env var that relocates Claude Code's mutable global state; when the operator
# has already exported it we defer to their value (OAuth-debug escape hatch).
_CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"

_log = get_logger("agents.cli.claude_code")


def _build_argv(
    target: str,
    prompt: str,
    *,
    model: str | None,
    max_turns: int | None,
    mcp_config_path: str | None,
) -> list[str]:
    """Build the ``claude`` headless invocation for ``prompt``.

    ``--verbose`` is mandatory: the CLI rejects ``--output-format stream-json``
    under ``-p`` without it. ``--dangerously-skip-permissions`` auto-approves
    every tool call so headless runs never block on a confirmation prompt. When
    an MCP config is bound, ``--strict-mcp-config`` restricts the CLI to exactly
    those servers, ignoring any stray project/user ``.mcp.json``.

    Args:
        target: Path to the ``claude`` binary (already user-expanded).
        prompt: Task prompt, passed as an argv value (never through a shell).
        model: Model id for ``--model``, or ``None`` to use the CLI default.
        max_turns: Cap for ``--max-turns``, or ``None`` for the CLI default.
        mcp_config_path: Absolute path to the MCP config document, or ``None``.

    Returns:
        The argv list ready to hand to ``core.subprocess.run``.
    """
    argv = [
        target,
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
    ]
    if model:
        argv.extend(["--model", model])
    if max_turns is not None:
        argv.extend(["--max-turns", str(max_turns)])
    if mcp_config_path:
        argv.extend(["--mcp-config", mcp_config_path, "--strict-mcp-config"])
    return argv


def _build_env(config: AgentConfig, *, config_dir: str | None) -> dict[str, str]:
    """Build the env overlay that makes the Claude Code run model-agnostic.

    ``config.api_key`` is routed onto the provider's API-key env var(s) via the
    shared contract (:func:`~devops_bench.core.model_providers.resolve_provider`,
    defaulted to ``anthropic`` for this harness). Vertex / Bedrock backends set
    their ``CLAUDE_CODE_USE_*`` switch and, for Vertex, map the repo's ambient
    ``GCP_PROJECT_ID`` / ``GCP_VERTEX_LOCATION`` onto the CLI's
    ``ANTHROPIC_VERTEX_PROJECT_ID`` / ``CLOUD_ML_REGION`` (the same source envs
    the in-process API adapter reads). The model is never set here — it flows
    through the ``--model`` argv flag.

    Args:
        config: Resolved :class:`AgentConfig` for this run.
        config_dir: Per-run ``CLAUDE_CONFIG_DIR`` path, or ``None`` when the
            operator exported their own (then the ambient value is left intact).

    Returns:
        A mapping suitable for ``core.subprocess.run``'s ``extra_env``.

    Raises:
        ConfigError: If ``config.provider`` is not a known provider.
    """
    # Resolve unconditionally so an unknown provider fails loud even on a keyless
    # (Vertex/Bedrock) run, not only when a key happens to be set.
    spec = resolve_provider(config.provider, default="anthropic")
    overlay: dict[str, str] = {
        # Headless hygiene: no background telemetry/error traffic, no autoupdate.
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_AUTOUPDATER": "1",
    }
    # Guard on truthiness: run() overlays extra_env onto os.environ, so writing
    # an empty key would clobber an ambient ANTHROPIC_API_KEY.
    if config.api_key:
        for var in spec.api_key_envs:
            overlay[var] = config.api_key
    if spec.backend == "vertex":
        overlay["CLAUDE_CODE_USE_VERTEX"] = "1"
        project = os.environ.get("GCP_PROJECT_ID")
        if project:
            overlay["ANTHROPIC_VERTEX_PROJECT_ID"] = project
        overlay["CLOUD_ML_REGION"] = os.environ.get("GCP_VERTEX_LOCATION", "global")
    elif spec.backend == "bedrock":
        overlay["CLAUDE_CODE_USE_BEDROCK"] = "1"
    if config_dir is not None:
        overlay[_CONFIG_DIR_ENV] = config_dir
    if config.extra_env:
        overlay.update(config.extra_env)
    return overlay


@contextlib.contextmanager
def _claude_config_dir() -> Iterator[str | None]:
    """Yield a fresh per-run ``CLAUDE_CONFIG_DIR``, or ``None`` if operator-set.

    An ambient ``CLAUDE_CONFIG_DIR`` is the operator's escape hatch (e.g. to
    reuse a cached OAuth login for local debugging); it is left untouched and
    ``None`` is yielded so no per-run temp dir is created or injected.
    """
    if _CONFIG_DIR_ENV in os.environ:
        yield None
        return
    with tempfile.TemporaryDirectory(prefix="claude-config-") as tmpdir:
        yield tmpdir


@AGENTS.register("claude")
class ClaudeCodeAgent(AgentHarness):
    """Claude Code CLI agent harness driving the ``claude`` binary.

    The binary path is resolved from ``config.target``, falling back to
    ``"claude"`` on ``$PATH``. Model / API key flow from ``config.model`` (via
    ``--model``) / ``config.api_key`` (via the env overlay) — never hardcoded.

    ``__init__`` assigns ``self.mcp_servers``, ``self.skills`` and ``self.rules``
    from the granted config bindings, which is what makes
    ``isinstance(agent, SupportsMcp / SupportsSkills / SupportsRules)`` return
    ``True`` for orchestrator-side capability negotiation (the Protocols are
    structural).

    The full canonical trajectory is parsed from the official
    ``--output-format stream-json`` event stream; no session files are read from
    disk, and every subprocess call goes through ``core.subprocess.run``.
    """

    def __init__(self, config: AgentConfig | None = None) -> None:
        AgentHarness.__init__(self, config)
        caps = self.config.capabilities
        self.mcp_servers = caps.mcp_servers
        self.skills = caps.skills
        self.rules = caps.rules

    def _execute(self, prompt: str, workspace_path: Path | None = None) -> AgentResult:
        """Build argv, run the CLI, and parse the stream-json output.

        The agent runs the binary inside ``workspace_path`` when the harness
        supplies one, else its own per-run temp working directory, laying down
        the granted capabilities there first via Claude Code's native cwd
        channels (all auto-loaded from cwd, so ``~/.claude`` stays untouched and
        concurrent runs never race):

        * ``CLAUDE.md`` — the operator brief, when ``rules.text`` is set.
        * ``.claude/skills/<name>/SKILL.md`` — one per discovered skill.
        * ``.claude/mcp-config.json`` — ``mcpServers`` for each command-bearing
          MCP binding, passed via ``--mcp-config --strict-mcp-config``.

        A temp working directory (used when ``workspace_path`` is ``None``) and
        the per-run ``CLAUDE_CONFIG_DIR`` are cleaned up when ``_execute``
        returns; a harness-supplied ``workspace_path`` is left for the harness.
        """
        caps = self.config.capabilities
        target = os.path.expanduser(self.config.target or "claude")
        rules_text = caps.rules.text

        with agent_workdir(workspace_path, prefix="claude-run-") as workdir:
            if rules_text:
                (workdir / _CLAUDE_RULES_FILE).write_text(rules_text, encoding="utf-8")

            claude_dir = workdir / _CLAUDE_CONFIG_DIRNAME
            materialize_skills(claude_dir / _CLAUDE_SKILLS_DIR, caps.skills.paths)

            mcp_config_path: str | None = None
            servers = build_mcp_servers(caps.mcp_servers)
            if servers:
                claude_dir.mkdir(parents=True, exist_ok=True)
                mcp_path = claude_dir / _CLAUDE_MCP_FILE
                mcp_path.write_text(json.dumps({"mcpServers": servers}, indent=2), encoding="utf-8")
                mcp_config_path = str(mcp_path)

            argv = _build_argv(
                target,
                prompt,
                model=self.config.model,
                max_turns=self.config.max_turns,
                mcp_config_path=mcp_config_path,
            )
            with _claude_config_dir() as config_dir:
                env_overlay = _build_env(self.config, config_dir=config_dir)
                try:
                    completed = run(
                        argv,
                        extra_env=env_overlay,
                        cwd=workdir,
                        check=False,
                        timeout=self.config.timeout_sec,
                    )
                except SubprocessError as exc:
                    return AgentResult.errored(f"claude subprocess error: {exc}")
                except OSError as exc:
                    # Missing / non-executable binary; core.subprocess.run does not wrap.
                    return AgentResult.errored(f"claude binary unavailable: {exc}")

        output, trajectory, tokens, parse_errors = parse_stream_json(completed.stdout or "")
        errors: list[str] = list(parse_errors)
        metadata: dict = {}
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            errors.append(f"claude exited {completed.returncode}: {stderr or '<no stderr>'}")
            if not output:
                output = f"Error: claude exited {completed.returncode}"
            metadata["returncode"] = completed.returncode
        return AgentResult(
            output=output,
            trajectory=trajectory,
            tokens=tokens,
            errors=errors,
            metadata=metadata,
        )
