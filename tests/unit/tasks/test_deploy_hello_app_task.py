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

"""The onboarded deploy-hello-app task parses into typed, dispatchable entries."""

from __future__ import annotations

from pathlib import Path

import yaml

from devops_bench.tasks.schema import Task
from devops_bench.verification import VerificationSpec

_TASK = Path("tasks/gcp/deploy-hello-app/task.yaml")


def _load() -> Task:
    raw = yaml.safe_load(_TASK.read_text())
    return Task.from_dict(raw, name_default="deploy-hello-app")


def _substitute(check: object) -> object:
    # Stand in for the harness placeholder pass so registry parse sees no {{...}}.
    if isinstance(check, dict):
        return {k: _substitute(v) for k, v in check.items()}
    if isinstance(check, list):
        return [_substitute(v) for v in check]
    if isinstance(check, str):
        return check.replace("{{GKE_CLUSTER_NAME}}", "c1")
    return check


def test_task_has_seven_objectives_and_two_safeguards():
    task = _load()
    entries = task.verification_entries
    assert entries is not None
    objectives = [e for e in entries if e.role == "objective"]
    safeguards = [e for e in entries if e.role == "safeguard"]
    assert len(objectives) == 7
    assert len(safeguards) == 2


def test_weights_match_vocab():
    task = _load()
    by_name = {e.name: e for e in task.verification_entries}
    assert by_name["pod-hardening"].weight == 3.0
    assert by_name["serving-http"].weight == 2.0


def test_safeguard_severities():
    task = _load()
    by_name = {e.name: e for e in task.verification_entries}
    assert by_name["not-dumped-in-default"].severity == "recoverable"
    assert by_name["blast-radius"].severity == "catastrophic"


def test_every_check_parses_through_the_registry():
    task = _load()
    for entry in task.verification_entries:
        node = VerificationSpec(_substitute(entry.check))
        assert node.root is not None
