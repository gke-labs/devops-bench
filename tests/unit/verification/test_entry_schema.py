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

"""Unit tests for VerificationEntry schema and the optimize-scale regression.

Critical regression: the only real task with a verification_spec
(tasks/common/optimize-scale/task.yaml) must parse under the new typed
list[VerificationEntry] schema and its entries must default to role='correctness'.
This test makes that claim explicit so the renovation cannot silently break it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from devops_bench.tasks.schema import Task
from devops_bench.verification.entry import VerificationEntry

# -- VerificationEntry model --------------------------------------------------


def test_entry_defaults_role_to_correctness():
    entry = VerificationEntry(name="check-pods", spec={"type": "pod_healthy", "selector": "app=x"})

    assert entry.role == "correctness"


def test_entry_accepts_all_roles():
    for role in ("correctness", "safety", "catastrophic"):
        entry = VerificationEntry(name="check", role=role, spec={})
        assert entry.role == role


def test_entry_rejects_unknown_role():
    with pytest.raises(ValidationError):
        VerificationEntry(name="check", role="unknown", spec={})


def test_entry_rejects_unchanged_mode():
    with pytest.raises(ValidationError, match="unchanged"):
        VerificationEntry(
            name="check",
            role="correctness",
            spec={"type": "scaling_complete", "deployment": "web", "mode": "unchanged"},
        )


def test_entry_rejects_unchanged_mode_nested_in_parallel():
    with pytest.raises(ValidationError, match="unchanged"):
        VerificationEntry(
            name="check",
            role="correctness",
            spec={
                "type": "parallel",
                "checks": [
                    {"type": "scaling_complete", "deployment": "web", "mode": "unchanged"},
                ],
            },
        )


def test_entry_spec_accepts_any_value():
    entry = VerificationEntry(name="raw", spec={"type": "parallel", "checks": []})
    assert entry.spec == {"type": "parallel", "checks": []}


def test_entry_spec_can_be_none():
    entry = VerificationEntry(name="raw", spec=None)
    assert entry.spec is None


def test_entry_name_is_required():
    with pytest.raises(ValidationError):
        VerificationEntry(role="correctness", spec={})


# -- Role type ----------------------------------------------------------------


def test_role_literal_values():
    valid = ["correctness", "safety", "catastrophic"]
    for v in valid:
        entry = VerificationEntry(name="x", role=v, spec={})
        assert entry.role == v


# -- Critical regression: optimize-scale task parses under typed schema -------


_TASK_YAML_PATH = Path(__file__).parents[3] / "tasks" / "common" / "optimize-scale" / "task.yaml"


@pytest.mark.skipif(
    not _TASK_YAML_PATH.exists(),
    reason="optimize-scale task.yaml not present in this checkout",
)
def test_optimize_scale_verification_spec_parses_as_typed_entries():
    """The optimize-scale task's verification_spec loads as list[VerificationEntry].

    This is the load-time regression gate for the 'renovation not replacement'
    claim. The spec must round-trip through Task.from_dict with the new typed
    field without any authoring change to the task.yaml.
    """
    raw = yaml.safe_load(_TASK_YAML_PATH.read_text())
    task = Task.from_dict(raw, name_default="optimize-scale", folder="optimize-scale")

    assert task.verification_spec is not None
    assert isinstance(task.verification_spec, list)
    assert len(task.verification_spec) == 1

    entry = task.verification_spec[0]
    assert isinstance(entry, VerificationEntry)
    assert entry.name == "Planned Load Spike Verification"
    assert entry.role == "correctness"

    # The inner spec is kept raw (unsubstituted, unparsed) at task-load time.
    assert isinstance(entry.spec, dict)
    assert entry.spec.get("type") == "parallel"


@pytest.mark.skipif(
    not _TASK_YAML_PATH.exists(),
    reason="optimize-scale task.yaml not present in this checkout",
)
def test_optimize_scale_entry_spec_retains_unsubstituted_placeholders():
    """Placeholder strings survive task load so the harness can substitute them."""
    raw = yaml.safe_load(_TASK_YAML_PATH.read_text())
    task = Task.from_dict(raw, name_default="optimize-scale", folder="optimize-scale")

    entry = task.verification_spec[0]
    spec_str = str(entry.spec)
    assert "{{TARGET_DEPLOYMENT_NAME}}" in spec_str or "{{NAMESPACE}}" in spec_str


# -- Task.from_dict with typed verification_spec ------------------------------


def test_task_from_dict_with_no_verification_spec_is_none():
    raw = {"id": "t1", "name": "t", "prompt": "p"}
    task = Task.from_dict(raw)

    assert task.verification_spec is None


def test_task_from_dict_with_list_of_entries():
    raw = {
        "id": "t2",
        "name": "t",
        "prompt": "p",
        "verification_spec": [
            {
                "name": "check-pods",
                "role": "safety",
                "spec": {"type": "pod_healthy", "selector": "app=x"},
            },
        ],
    }
    task = Task.from_dict(raw)

    assert task.verification_spec is not None
    assert len(task.verification_spec) == 1
    assert task.verification_spec[0].name == "check-pods"
    assert task.verification_spec[0].role == "safety"


def test_task_from_dict_with_entries_defaults_role():
    raw = {
        "id": "t3",
        "name": "t",
        "prompt": "p",
        "verification_spec": [
            {"name": "check", "spec": {"type": "pod_healthy", "selector": "app=x"}},
        ],
    }
    task = Task.from_dict(raw)

    assert task.verification_spec[0].role == "correctness"
