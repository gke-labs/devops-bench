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

"""Hermes CLI agent harness driving the ``hermes`` binary (local-only)."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from devops_bench.agents.base import AGENTS, AgentHarness
from devops_bench.agents.cli.hermes.parsing import (
    empty_tokens,
    extract_tokens_from_db,
    extract_trajectory_from_db,
)
from devops_bench.agents.config import AgentConfig
from devops_bench.agents.result import AgentResult
from devops_bench.agents.shared.cli_capabilities import (
    build_mcp_servers,
    materialize_skills,
)
from devops_bench.core import get_logger
from devops_bench.core.errors import SubprocessError
from devops_bench.core.model_providers import resolve_provider
from devops_bench.core.subprocess import run as devops_run

if TYPE_CHECKING:
    from devops_bench.agents.capabilities import McpBinding

_log = get_logger("agents.cli.hermes.agent")

_HERMES_CONFIG_FILE = "config.yaml"
_HERMES_ENV_FILE = ".env"
_HERMES_STATE_DB = "state.db"
_SOUL_FILE = "SOUL.md"


def _prepend_rules(rules_text: str, prompt: str) -> str:
    """Prepend rules to the prompt as a system brief."""
    if not rules_text or not rules_text.strip():
        return prompt
    return f"{rules_text.rstrip()}\n\n{prompt}"


def _build_env(config: AgentConfig) -> dict[str, str]:
    """Build env overlay with provider-specific API keys."""
    overlay: dict[str, str] = {}
    if config.provider and config.api_key:
        spec = resolve_provider(config.provider)
        for var in spec.api_key_envs:
            overlay[var] = config.api_key

    if config.extra_env:
        overlay.update(config.extra_env)
    return overlay


@AGENTS.register("hermes")
class HermesAgent(AgentHarness):
    """Hermes CLI agent harness driving the local ``hermes`` binary.

    Capabilities are delivered through:
    - MCP: written to a run-scoped config.yaml
    - Skills: materialized in the run-scoped skills/ dir
    - Rules: prepended to the prompt
    """

    def __init__(
        self, config: AgentConfig | None = None, *, inherit_user_config: bool = False
    ) -> None:
        AgentHarness.__init__(self, config)
        self.inherit_user_config = inherit_user_config
        caps = self.config.capabilities
        self.rules = caps.rules
        self.mcp_servers = caps.mcp_servers
        self.skills = caps.skills

    def _resolve_hermes_bin(self) -> str:
        """Resolve the ``hermes`` binary path."""
        if self.config.target:
            return os.path.expanduser(self.config.target)
        candidate = os.path.expanduser("~/.local/bin/hermes")
        return candidate if os.path.exists(candidate) else "hermes"

    def _prepare_config(self, run_dir: Path, mcp_servers: tuple[McpBinding, ...]) -> None:
        """Initialize run-scoped config and merge MCP servers."""
        user_hermes_dir = Path(os.path.expanduser("~/.hermes"))

        if self.inherit_user_config:
            if (user_hermes_dir / _HERMES_CONFIG_FILE).exists():
                shutil.copy(user_hermes_dir / _HERMES_CONFIG_FILE, run_dir / _HERMES_CONFIG_FILE)
            if (user_hermes_dir / _HERMES_ENV_FILE).exists():
                shutil.copy(user_hermes_dir / _HERMES_ENV_FILE, run_dir / _HERMES_ENV_FILE)
            if (user_hermes_dir / _SOUL_FILE).exists():
                shutil.copy(user_hermes_dir / _SOUL_FILE, run_dir / _SOUL_FILE)

        config_path = run_dir / _HERMES_CONFIG_FILE
        config_data = {}
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config_data = yaml.safe_load(f) or {}
            except Exception as exc:
                _log.warning("Failed to load existing config.yaml: %s", exc)

        mcp_config = build_mcp_servers(mcp_servers)
        if mcp_config:
            kubeconfig = os.environ.get("KUBECONFIG")
            if kubeconfig:
                for entry in mcp_config.values():
                    entry.setdefault("env", {})["KUBECONFIG"] = kubeconfig

            config_data["mcp_servers"] = {**(config_data.get("mcp_servers") or {}), **mcp_config}

        with open(config_path, "w") as f:
            yaml.safe_dump(config_data, f)

    def _execute(self, prompt: str, workspace_path: Path | None = None) -> AgentResult:
        hermes_bin = self._resolve_hermes_bin()
        caps = self.config.capabilities
        final_prompt = _prepend_rules(caps.rules.text, prompt)

        # A harness-supplied workspace_path is used as-is (the harness owns its
        # lifecycle); otherwise fall back to a throwaway temp dir.
        with tempfile.TemporaryDirectory(prefix="hermes-run-") as rundir:
            run_path = workspace_path if workspace_path is not None else Path(rundir)

            self._prepare_config(run_path, caps.mcp_servers)

            skills_dir = run_path / "skills"
            skills_dir.mkdir(exist_ok=True)
            materialize_skills(skills_dir, caps.skills.paths)

            # Build environment
            env_overlay = _build_env(self.config)
            env_overlay["HERMES_HOME"] = str(run_path)

            # Build command
            cmd = [hermes_bin, "chat", "-q", final_prompt]

            if self.config.model:
                cmd.extend(["-m", self.config.model])

            if self.config.provider:
                spec = resolve_provider(self.config.provider)
                hermes_prov = "vertex" if spec.backend == "vertex" else spec.adapter_family
                cmd.extend(["--provider", hermes_prov])

            try:
                completed = devops_run(
                    cmd,
                    check=False,
                    timeout=self.config.timeout_sec,
                    extra_env=env_overlay,
                )
            except SubprocessError as exc:
                # If check=False, SubprocessError is only raised on timeout
                stdout_text = exc.stdout or ""
                stderr_text = exc.stderr or ""
                trajectory = []
                export_errors = []
                db_path = run_path / _HERMES_STATE_DB
                if db_path.exists():
                    try:
                        trajectory, export_errors = extract_trajectory_from_db(db_path)
                    except Exception as db_exc:
                        _log.warning("Failed to extract trajectory on timeout: %s", db_exc)
                        export_errors.append(f"Failed to extract trajectory on timeout: {db_exc}")
                # Independent of trajectory extraction: never raises, and reports
                # whatever the killed run flushed (all-None when nothing did).
                tokens = extract_tokens_from_db(db_path)

                return AgentResult(
                    output=f"Timeout expired.\n\n=== STDOUT ===\n{stdout_text}\n\n=== STDERR ===\n{stderr_text}",
                    trajectory=trajectory,
                    tokens=tokens,
                    errors=[f"hermes agent timed out after {self.config.timeout_sec}s"]
                    + export_errors,
                    metadata={"timeout": True},
                )
            except OSError as exc:
                # Same canonical all-None token shape as every other path.
                return AgentResult(
                    output=f"Error: hermes binary unavailable: {exc}",
                    trajectory=[],
                    tokens=empty_tokens(),
                    errors=[f"hermes binary unavailable: {exc}"],
                )

            stdout_text = completed.stdout or ""
            errors: list[str] = []
            metadata: dict = {}

            if completed.returncode != 0:
                stderr = (completed.stderr or "").strip()
                errors.append(
                    f"hermes agent exited {completed.returncode}: {stderr or '<no stderr>'}"
                )
                metadata["returncode"] = completed.returncode

            db_path = run_path / _HERMES_STATE_DB
            trajectory, export_errors = extract_trajectory_from_db(db_path)
            errors.extend(export_errors)
            tokens = extract_tokens_from_db(db_path)

        return AgentResult(
            output=stdout_text,
            trajectory=trajectory,
            tokens=tokens,
            errors=errors,
            metadata=metadata,
        )
