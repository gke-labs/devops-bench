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

"""Tests for the CLI capability helpers shared by the Gemini/openclaw agents."""

from __future__ import annotations

from pathlib import Path

from devops_bench.agents.capabilities import McpBinding
from devops_bench.agents.shared.cli_capabilities import (
    build_mcp_servers,
    materialize_skills,
)


def test_build_mcp_servers_maps_command_to_command_and_args():
    """``command[0]`` → ``command``; the remainder → ``args``."""
    servers = build_mcp_servers(
        (McpBinding(name="gke", command=("gke-mcp", "--flag", "v"), tools=("t",)),)
    )
    assert servers == {"gke": {"command": "gke-mcp", "args": ["--flag", "v"]}}


def test_build_mcp_servers_omits_args_for_bare_command():
    """A single-element command yields no ``args`` key."""
    servers = build_mcp_servers((McpBinding(name="gke", command=("gke-mcp",)),))
    assert servers == {"gke": {"command": "gke-mcp"}}


def test_build_mcp_servers_skips_command_less_bindings():
    """Empty-command bindings (in-process/built-in servers) are not launched."""
    servers = build_mcp_servers((McpBinding(name="builtin", command=(), tools=("t",)),))
    assert servers == {}


def test_build_mcp_servers_names_unnamed_bindings_by_index():
    """A binding with no name falls back to a positional ``mcp<index>`` key."""
    servers = build_mcp_servers((McpBinding(name="", command=("srv",)),))
    assert servers == {"mcp0": {"command": "srv"}}


def test_materialize_skills_writes_named_skill_files(tmp_path: Path):
    """Each discovered ``SKILL.md`` is copied under ``<root>/<name>/SKILL.md``."""
    src = tmp_path / "src"
    (src / "rotate").mkdir(parents=True)
    (src / "rotate" / "SKILL.md").write_text(
        "---\nname: rotate-secret\ndescription: rotate\n---\nbody\n",
        encoding="utf-8",
    )
    dest = tmp_path / "dest"

    written = materialize_skills(dest, (str(src),))

    assert written == ["rotate-secret"]
    copied = dest / "rotate-secret" / "SKILL.md"
    assert "body" in copied.read_text(encoding="utf-8")


def test_materialize_skills_skips_missing_paths(tmp_path: Path):
    """A non-existent source path is warned and skipped, not fatal."""
    assert materialize_skills(tmp_path / "dest", (str(tmp_path / "nope"),)) == []
