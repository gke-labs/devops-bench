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

"""Capability materialization shared by the CLI agents (Gemini, openclaw).

Both CLI agents render granted MCP bindings into a ``{name: {command, args}}``
launch map and copy discovered ``SKILL.md`` files into the binary's workspace
skills tree. Importing this module pulls no provider SDK.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from devops_bench.agents.shared.skills import parse_skill_md
from devops_bench.core import get_logger

if TYPE_CHECKING:
    from devops_bench.agents.capabilities import McpBinding

__all__ = ["build_mcp_servers", "materialize_skills"]

_log = get_logger("agents.shared.cli_capabilities")

_SKILL_FILE = "SKILL.md"


def build_mcp_servers(mcp_servers: tuple[McpBinding, ...]) -> dict[str, dict]:
    """Map MCP bindings with a launch command to a CLI ``servers`` mapping.

    Bindings with an empty ``command`` are skipped: a CLI needs a command to
    spawn a stdio MCP server, and an empty-command binding denotes a server the
    binary already hosts itself.

    Args:
        mcp_servers: Bindings granted for the run.

    Returns:
        A ``{name: {"command": ..., "args": [...]}}`` mapping suitable for the
        agent's MCP-servers config section. Empty when no binding carries a
        command.
    """
    servers: dict[str, dict] = {}
    for index, binding in enumerate(mcp_servers):
        if not binding.command:
            continue
        name = binding.name or f"mcp{index}"
        entry: dict = {"command": binding.command[0]}
        if len(binding.command) > 1:
            entry["args"] = list(binding.command[1:])
        servers[name] = entry
    return servers


def materialize_skills(skills_root: Path, paths: tuple[str, ...]) -> list[str]:
    """Copy discovered ``SKILL.md`` files into a CLI's workspace skills tree.

    For each ``SKILL.md`` found beneath ``paths`` (the same discovery the API
    agent performs), the file is written to ``skills_root/<name>/SKILL.md`` using
    the ``name`` from its frontmatter.

    Args:
        skills_root: The destination skills directory to populate.
        paths: Skill source directories to walk recursively. Missing paths are
            warned and skipped (matching the API agent's discovery semantic).

    Returns:
        The names of the skills materialized, in discovery order.
    """
    written: list[str] = []
    for raw_path in paths:
        if not raw_path:
            continue
        source = Path(os.path.expanduser(raw_path))
        if not source.exists():
            _log.warning("Skills directory not found: %s", source)
            continue
        for skill_file in sorted(source.rglob(_SKILL_FILE)):
            name, _description, content = parse_skill_md(str(skill_file))
            if not name or content is None:
                continue
            dest_dir = skills_root / name
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / _SKILL_FILE).write_text(content, encoding="utf-8")
            written.append(name)
            _log.info("Linked skill %s -> %s", name, dest_dir)
    return written
