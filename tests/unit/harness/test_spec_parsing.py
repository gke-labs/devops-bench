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

"""Harness parses opaque task blobs into typed component contracts.

CONVENTIONS.md §3 / §4: every Layer-2 seam consumes a **typed** node, so the
harness must convert the opaque ``chaos_spec`` / ``verification_spec`` blobs
(``Any`` at the Layer-1 task boundary) into ``ChaosSpec`` / ``VerificationSpec``
at its own boundary.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from devops_bench.chaos import ChaosSpec
from devops_bench.chaos.faults.generate_load import GenerateLoadFault
from devops_bench.chaos.triggers.time_delay import TimeTrigger
from devops_bench.harness.default import DefaultHarness
from devops_bench.tasks import FileSystemTaskLoader
from devops_bench.verification import (
    ParallelSpec,
    VerificationSpec,
)
from devops_bench.verification.verifiers import (
    PodHealthyVerifier,
    ScalingCompleteVerifier,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TASK_DIR = _REPO_ROOT / "complextasks" / "optimize-scale"
_TASK_YAML = _TASK_DIR / "task.yaml"


def _harness() -> DefaultHarness:
    return DefaultHarness(project_id="proj", cluster_name="cluster")


def test_optimize_scale_chaos_parses_through_harness() -> None:
    """The harness migrates the real optimize-scale chaos blob to typed nodes."""
    raw = yaml.safe_load(_TASK_YAML.read_text())
    specs = _harness()._parse_chaos_specs(raw["chaos_spec"], cluster_name="c")  # noqa: SLF001

    assert len(specs) == 1
    spec = specs[0]
    assert isinstance(spec, ChaosSpec)
    assert isinstance(spec.trigger, TimeTrigger)
    assert spec.trigger.delay_seconds == 5
    assert isinstance(spec.action, GenerateLoadFault)
    assert spec.action.target.qps == 300
    # Placeholders flow through the rewrite, even though chaos_spec is now
    # native YAML (Decision D2 — values migrated, field name kept).
    assert "{{" not in spec.action.target.service_url
    assert spec.verify == "Planned Load Spike Verification"


def test_optimize_scale_verification_mapping_keys_typed_specs() -> None:
    """``_build_verification_mapping`` returns ``(mapping, errors)`` with typed specs.

    The errors list is empty on the canonical optimize-scale shape; a
    separate test exercises the loud-fail path.
    """
    raw = yaml.safe_load(_TASK_YAML.read_text())
    mapping, errors = _harness()._build_verification_mapping(  # noqa: SLF001
        raw["verification_spec"], cluster_name="c"
    )

    assert errors == []
    assert set(mapping.keys()) == {"Planned Load Spike Verification"}
    node = mapping["Planned Load Spike Verification"]
    assert isinstance(node, VerificationSpec)
    root = node.root
    assert isinstance(root, ParallelSpec)
    leaf_types = [type(leaf) for leaf in root.checks]
    assert PodHealthyVerifier in leaf_types
    assert ScalingCompleteVerifier in leaf_types


def test_verification_mapping_canonical_wrapped_shape() -> None:
    """The canonical ``[{name, spec: <typed-node>}]`` shape parses end-to-end."""
    raw = [
        {
            "name": "all-healthy",
            "spec": {
                "type": "parallel",
                "checks": [
                    {
                        "type": "pod_healthy",
                        "selector": "app=demo",
                        "namespace": "default",
                    }
                ],
            },
        }
    ]
    mapping, errors = _harness()._build_verification_mapping(  # noqa: SLF001
        raw, cluster_name="c"
    )
    assert errors == []
    assert set(mapping.keys()) == {"all-healthy"}
    assert isinstance(mapping["all-healthy"], VerificationSpec)


def test_verification_mapping_bare_node_compat_shape_still_parses() -> None:
    """Legacy bare-node entries (no ``spec:`` wrapper) still parse.

    Pins the back-compat branch — the entry mapping itself acts as the
    typed verification node when no ``spec`` key is present. Documented
    explicitly in :meth:`_build_verification_mapping` so reviewers can
    spot the two-shape acceptance.
    """
    raw = [
        {
            "name": "pods",
            "type": "pod_healthy",
            "selector": "app=demo",
            "namespace": "default",
        }
    ]
    mapping, errors = _harness()._build_verification_mapping(  # noqa: SLF001
        raw, cluster_name="c"
    )
    assert errors == []
    assert set(mapping.keys()) == {"pods"}


def test_verification_mapping_surfaces_validation_failures() -> None:
    """A malformed entry never silently disappears — it lands on ``errors``."""
    raw = [
        {"name": "good", "spec": {"type": "pod_healthy", "selector": "app=x"}},
        # Missing ``type`` discriminator — pydantic rejects.
        {"name": "bad", "spec": {"selector": "app=y"}},
        # Missing ``name`` — skipped + recorded as an authoring error.
        {"spec": {"type": "pod_healthy", "selector": "app=z"}},
        # Non-mapping entry — skipped + recorded.
        "not a mapping",
    ]
    mapping, errors = _harness()._build_verification_mapping(  # noqa: SLF001
        raw, cluster_name="c"
    )
    assert set(mapping.keys()) == {"good"}
    # Every authoring failure shows up — operator sees the broken entries
    # on the run record, not just a log line.
    error_names = {e["name"] for e in errors}
    assert "bad" in error_names
    # Index-keyed labels for the unnamed / non-mapping entries.
    assert any(name.startswith("<index ") for name in error_names)


def test_legacy_json_in_yaml_chaos_spec_still_parses() -> None:
    """A legacy JSON-in-YAML string round-trips through the harness parser.

    Decision D2 keeps the *field name* stable; the harness accepts both the
    legacy string-valued shape and the post-migration native-YAML shape so an
    older fork can land the harness PR without touching its task files.
    """
    legacy_blob = (
        '[{"name":"X","trigger":{"type":"time","delay_seconds":1},'
        '"action":{"type":"generate_load","target":{"service_url":"http://h","qps":1}}}]'
    )
    specs = _harness()._parse_chaos_specs(legacy_blob, cluster_name="c")  # noqa: SLF001
    assert len(specs) == 1
    assert specs[0].name == "X"


def test_task_loader_reads_native_yaml_specs_as_python_values() -> None:
    """The Layer-1 task loader carries the native-YAML blob through unchanged."""
    tasks = FileSystemTaskLoader().load_tasks(str(_TASK_DIR))
    assert len(tasks) == 1
    task = tasks[0]
    # Opaque ``Any``: a list-of-mappings flows through verbatim, not as a string.
    assert isinstance(task.chaos_spec, list)
    assert isinstance(task.verification_spec, list)
