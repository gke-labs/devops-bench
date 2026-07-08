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

"""Token-accounting tests for the legacy OpenClaw session parser.

The ``pkg/agents`` tree is excluded from pytest collection (see ``pytest.ini``),
so this test lives under ``tests/`` but imports the legacy module directly.
"""

from __future__ import annotations

import json

from pkg.agents.runner.openclaw import _parse_openclaw_session


def _assistant(usage: dict) -> dict:
    return {"type": "message", "message": {"role": "assistant", "usage": usage, "content": []}}


def test_parse_session_sums_usage_across_assistant_turns():
    """Usage is summed across every assistant turn, not taken from the last one.

    OpenClaw records ``usage`` per assistant message (per model call); keeping
    only the final message undercounts a multi-turn session to a single call.
    """
    session = "\n".join(
        json.dumps(line)
        for line in (
            _assistant(
                {
                    "input": 2000,
                    "output": 300,
                    "cacheRead": 28000,
                    "cacheWrite": 0,
                    "totalTokens": 30300,
                }
            ),
            _assistant(
                {
                    "input": 1500,
                    "output": 250,
                    "cacheRead": 41000,
                    "cacheWrite": 0,
                    "totalTokens": 42750,
                }
            ),
            _assistant(
                {
                    "input": 900,
                    "output": 120,
                    "cacheRead": 60000,
                    "cacheWrite": 0,
                    "totalTokens": 61020,
                }
            ),
        )
    )

    tokens, _trajectory = _parse_openclaw_session(session)

    assert tokens == {
        "input": 4400,
        "output": 670,
        "cacheRead": 129000,
        "cacheWrite": 0,
        "totalTokens": 134070,
    }


def test_parse_session_sums_nested_cost_breakdown():
    """Nested numeric mappings (e.g. a per-turn ``cost`` block) are summed too."""
    session = "\n".join(
        json.dumps(line)
        for line in (
            _assistant({"input": 10, "cost": {"input": 0.0, "total": 0.01}}),
            _assistant({"input": 5, "cost": {"input": 0.0, "total": 0.02}}),
        )
    )

    tokens, _trajectory = _parse_openclaw_session(session)

    assert tokens["input"] == 15
    assert tokens["cost"]["total"] == 0.03


def test_parse_session_empty_when_no_usage():
    """A session with no assistant usage yields empty tokens (no crash)."""
    session = json.dumps({"type": "message", "message": {"role": "user", "content": []}})

    tokens, _trajectory = _parse_openclaw_session(session)

    assert tokens == {}
