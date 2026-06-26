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

"""Tests for skill loading and GEval metric construction (outcome + tool)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from devops_bench.metrics import _skills, outcome_validity, tool_invocation
from devops_bench.metrics.base import GEVAL_PASS_THRESHOLD
from devops_bench.metrics.tool_invocation import TOOL_INVOCATION_THRESHOLD


def _patch_resources(mocker, files_by_name):
    """Patch ``_skills.resources.files`` with a fake package traversable.

    ``files_by_name`` maps a filename to its text content; any name absent from
    the mapping is treated as a missing resource (``is_file()`` is False).
    """

    class _FakeResource:
        def __init__(self, name):
            self._name = name

        def is_file(self):
            return self._name in files_by_name

        def read_text(self, encoding="utf-8"):
            return files_by_name[self._name]

    class _FakePackage:
        def __truediv__(self, name):
            return _FakeResource(name)

    mocker.patch.object(_skills.resources, "files", return_value=_FakePackage())


def test_load_skill_text_reads_packaged_resource(mocker):
    _patch_resources(
        mocker, {"outcome-validity-checklist.md": "## Evaluation Criteria"}
    )
    assert (
        _skills.load_skill_text("outcome-validity-checklist.md")
        == "## Evaluation Criteria"
    )


def test_load_outcome_criteria_uses_loader(mocker):
    _patch_resources(
        mocker, {outcome_validity.OUTCOME_SKILL_FILENAME: "OUTCOME-MD"}
    )
    assert outcome_validity.load_outcome_criteria() == "OUTCOME-MD"


def test_load_tool_criteria_uses_loader(mocker):
    _patch_resources(mocker, {tool_invocation.TOOL_SKILL_FILENAME: "TOOL-MD"})
    assert tool_invocation.load_tool_criteria() == "TOOL-MD"


def test_load_skill_text_missing_raises(mocker):
    _patch_resources(mocker, {})  # nothing exists
    with pytest.raises(FileNotFoundError):
        _skills.load_skill_text("does-not-exist.md")


def test_build_outcome_validity_metric(mocker):
    geval_cls = mocker.patch.object(outcome_validity, "GEval")
    mocker.patch.object(outcome_validity, "load_outcome_criteria", return_value="CRIT")
    model = MagicMock()

    outcome_validity.build_outcome_validity_metric(model)

    kwargs = geval_cls.call_args.kwargs
    assert kwargs["name"] == "OutcomeValidity"
    assert kwargs["criteria"] == "CRIT"
    assert kwargs["threshold"] == GEVAL_PASS_THRESHOLD
    assert kwargs["model"] is model


def test_build_tool_invocation_metric_applies_threshold(mocker):
    geval_cls = mocker.patch.object(tool_invocation, "GEval")
    mocker.patch.object(tool_invocation, "load_tool_criteria", return_value="CRIT")
    model = MagicMock()

    tool_invocation.build_tool_invocation_metric(model)

    kwargs = geval_cls.call_args.kwargs
    assert kwargs["name"] == "ToolInvocation"
    assert kwargs["threshold"] == TOOL_INVOCATION_THRESHOLD
    assert kwargs["model"] is model
