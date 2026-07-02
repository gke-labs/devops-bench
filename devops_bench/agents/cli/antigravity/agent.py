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

"""Antigravity CLI agent harness driving the ``agy`` binary."""

from __future__ import annotations

import json
import os
import pathlib
from typing import TYPE_CHECKING
import tempfile

from devops_bench import core
from devops_bench.agents import base
from devops_bench.agents import config as agents_config
from devops_bench.agents import result as agents_result
from devops_bench.agents.cli.antigravity import parsing
from devops_bench.agents.shared import cli_capabilities
from devops_bench.core import subprocess as devops_subprocess

if TYPE_CHECKING:
    from devops_bench.agents import capabilities

__all__ = ["AgyCliAgent"]

_log = core.get_logger("agents.cli.antigravity")


def _build_settings(
    mcp_servers: tuple[capabilities.McpBinding, ...],
    model: str | None,
    project: str | None = None,
    location: str | None = None,
) -> dict:
    """Assemble the Antigravity ``settings.json`` payload for a run."""
    settings: dict = {
        "experimental": {
            "skills": True
        }
    }
    servers = cli_capabilities.build_mcp_servers(mcp_servers)
    if servers:
        settings["mcpServers"] = servers
    if model:
        # Resolve model name (e.g. "google/gemini-3.5-flash" -> "gemini-3.5-flash")
        model_name = model.split("/")[-1]
        settings["modelConfigs"] = {"defaultModel": model_name}
        
    # Add GCP block if project/location are provided (needed for GCA/GKE tools)
    if project or location:
        settings["gcp"] = {}
        if project:
            settings["gcp"]["project"] = project
        if location:
            settings["gcp"]["location"] = location
            
    return settings


def _build_env(config: agents_config.AgentConfig) -> dict[str, str]:
    """Build the env overlay for the Antigravity CLI subprocess.

    Passes through necessary auth variables. HOME must NOT be overridden
    to leverage cached OAuth/ADC credentials.
    """
    overlay: dict[str, str] = {
        # Trust workspace so it doesn't block on untrusted folder warnings
        "GEMINI_CLI_TRUST_WORKSPACE": "true",
        # Disable OTLP exporters to avoid hangs in headless environments
        "OTEL_TRACES_EXPORTER": "none",
        "OTEL_METRICS_EXPORTER": "none",
        "OTEL_LOGS_EXPORTER": "none",
        "OTEL_SDK_DISABLED": "true",
    }
    
    # Pass through auth/project env vars if present
    auth_vars = [
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_GENAI_USE_VERTEXAI",
    ]
    for var in auth_vars:
        if var in os.environ:
            overlay[var] = os.environ[var]
            
    if config.api_key:
        overlay["GEMINI_API_KEY"] = config.api_key
        overlay["GOOGLE_API_KEY"] = config.api_key
    if config.model:
        overlay["GEMINI_MODEL"] = config.model
        
    if config.extra_env:
        overlay.update(config.extra_env)
        
    return overlay


def _get_gcloud_project() -> str | None:
    """Retrieve the default project from gcloud config if available."""
    try:
        import subprocess
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            project = result.stdout.strip()
            if project:
                return project
    except Exception:
        pass
    return None

def _get_gcloud_location() -> str | None:
    """Retrieve the default region from gcloud config if available."""
    try:
        import subprocess
        result = subprocess.run(
            ["gcloud", "config", "get-value", "compute/region"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            region = result.stdout.strip()
            if region:
                return region
    except Exception:
        pass
    return None


class _WorkspaceContext:
    """Context manager to handle temporary workspaces."""

    def __init__(self):
        self.tmpdir = tempfile.TemporaryDirectory(prefix="agy-run-")
        self.path = pathlib.Path(self.tmpdir.name)

    def __enter__(self) -> pathlib.Path:
        return self.path

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.tmpdir.cleanup()


@base.AGENTS.register("antigravity")
class AgyCliAgent(base.AgentHarness):
    """Antigravity CLI agent harness driving the ``agy`` binary.

    Lays down capabilities (rules, MCP, skills) in the workspace
    directory and spawns the ``agy`` binary. It preserves the user's real
    HOME to leverage cached OAuth/ADC credentials. The trajectory is
    extracted by parsing the generated transcript JSONL log file.
    """

    def __init__(self, config: agents_config.AgentConfig | None = None) -> None:
        super().__init__(config)
        caps = self.config.capabilities
        self.mcp_servers = caps.mcp_servers
        self.skills = caps.skills
        self.rules = caps.rules

    def _resolve_binary(self) -> str:
        """Resolve the absolute path to the ``agy`` binary."""
        if self.config.target:
            return os.path.expanduser(self.config.target)
        # Default installation path for antigravity-cli
        candidate = os.path.expanduser("~/.local/bin/agy")
        if os.path.exists(candidate):
            return candidate
        return "agy"

    def _execute(self, prompt: str) -> agents_result.AgentResult:
        caps = self.config.capabilities
        binary = self._resolve_binary()
        
        env_overlay = _build_env(self.config)
        
        with _WorkspaceContext() as workdir:
            gemini_dir = workdir / ".gemini"
            
            # Resolve project and location
            project = (
                os.environ.get("GOOGLE_CLOUD_PROJECT")
                or os.environ.get("GCP_PROJECT")
                or _get_gcloud_project()
            )
            if project:
                env_overlay["GOOGLE_CLOUD_PROJECT"] = project
                env_overlay["GCP_PROJECT"] = project

            location = (
                os.environ.get("GOOGLE_CLOUD_LOCATION")
                or os.environ.get("GCP_LOCATION")
                or _get_gcloud_location()
                or "us-central1"
            )
            if location:
                env_overlay["GOOGLE_CLOUD_LOCATION"] = location
                env_overlay["GCP_LOCATION"] = location
                
            # Build argv with explicit gemini_dir to ensure it runs in the workspace
            # and uses the local settings.json.
            argv = [
                binary,
                "--dangerously-skip-permissions",
                f"--gemini_dir={gemini_dir}",
            ]
            if project:
                argv.append(f"--project={project}")
            if self.config.model:
                model_name = self.config.model.split("/")[-1]
                argv.append(f"--model={model_name}")
            argv.append(f"--prompt={prompt}")
            
            # 1. Write rules/system prompt
            # Write to both GEMINI.md (legacy) and .agents/AGENTS.md (modern)
            if caps.rules.text:
                (workdir / "GEMINI.md").write_text(caps.rules.text, encoding="utf-8")
                agents_dir = workdir / ".agents"
                agents_dir.mkdir(parents=True, exist_ok=True)
                (agents_dir / "AGENTS.md").write_text(caps.rules.text, encoding="utf-8")

            # 2. Materialize skills in all candidate locations
            if caps.skills.paths:
                # Modern workspace path
                cli_capabilities.materialize_skills(workdir / ".agents" / "skills", caps.skills.paths)
                # Home-relative paths (rebranded and legacy)
                cli_capabilities.materialize_skills(workdir / ".agy" / "antigravity-cli" / "skills", caps.skills.paths)
                cli_capabilities.materialize_skills(workdir / ".gemini" / "antigravity-cli" / "skills", caps.skills.paths)

            # 3. Write settings.json to local workspace and home-relative candidate locations
            settings = _build_settings(caps.mcp_servers, self.config.model, project, location)
            if settings:
                for parent_dir in (
                    workdir / ".gemini",                  # Gemini workspace style
                    workdir / ".agents",                  # Jetski workspace style
                    workdir / ".agy" / "antigravity-cli", # Home-relative style (local fallback)
                    workdir / ".gemini" / "antigravity-cli",
                    workdir / ".config" / "antigravity-cli",
                ):
                    parent_dir.mkdir(parents=True, exist_ok=True)
                    (parent_dir / "settings.json").write_text(
                        json.dumps(settings, indent=2), encoding="utf-8"
                    )
            # Symlink the oauth token from the real home directory to the workspace gemini_dir
            # so we can authenticate without polluting the home directory with logs/state.
            real_home = pathlib.Path.home()
            real_token = real_home / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
            if real_token.exists():
                target_token_dir = gemini_dir / "antigravity-cli"
                target_token_dir.mkdir(parents=True, exist_ok=True)
                target_token = target_token_dir / "antigravity-oauth-token"
                if not target_token.exists():
                    try:
                        target_token.symlink_to(real_token)
                        _log.info("Symlinked OAuth token from %s to %s", real_token, target_token)
                    except OSError as exc:
                        _log.warning("Failed to symlink OAuth token: %s", exc)
            else:
                _log.warning("Real OAuth token not found at %s", real_token)

            # 4. Run the CLI
            try:
                completed = devops_subprocess.run(
                    argv,
                    extra_env=env_overlay,
                    cwd=workdir,
                    check=False,
                    timeout=self.config.timeout_sec,
                )
            except core.SubprocessError as exc:
                return agents_result.AgentResult.errored(f"antigravity-cli subprocess error: {exc}")
            except OSError as exc:
                return agents_result.AgentResult.errored(f"antigravity-cli binary unavailable: {exc}")

            # 5. Locate the generated session log file in the workspace's gemini_dir
            # Since we passed --gemini_dir, all logs and conversations are stored there.
            conv_dir = gemini_dir / "antigravity-cli" / "conversations"
            
            session_text = ""
            if conv_dir.exists():
                db_files = list(conv_dir.glob("*.db"))
                if db_files:
                    # Sort by modification time, newest first
                    db_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    latest_uuid = db_files[0].stem
                    transcript_path = (
                        gemini_dir / "antigravity-cli" / "brain" / latest_uuid 
                        / ".system_generated" / "logs" / "transcript.jsonl"
                    )
                    if transcript_path.exists():
                        session_text = transcript_path.read_text(encoding="utf-8")
                    else:
                        _log.warning("Transcript file not found: %s", transcript_path)
                else:
                    _log.warning("No .db files found in %s", conv_dir)
            else:
                _log.warning("Conversations directory not found: %s", conv_dir)

            if not session_text:
                _log.warning("Failed to retrieve session log, falling back to empty")

        # 6. Parse the session log to extract trajectory and metrics
        output, trajectory, tokens, parse_errors = parsing.parse_session_jsonl(session_text)
        
        errors: list[str] = list(parse_errors)
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            errors.append(f"agy exited {completed.returncode}: {stderr or '<no stderr>'}")
            if not output:
                output = f"Error: agy exited {completed.returncode}"
                
        # If we couldn't find a session file but the run succeeded, we might have no output.
        # Fall back to stdout if output is empty.
        if not output and completed.stdout:
            output = completed.stdout.strip()

        metadata: dict = {}
        if completed.returncode != 0:
            metadata["returncode"] = completed.returncode
            
        return agents_result.AgentResult(
            output=output,
            trajectory=trajectory,
            tokens=tokens,
            errors=errors,
            metadata=metadata,
        )
