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

"""Regression: the REAL ``optimize-scale`` chaos entry parses through ChaosSpec.

Pins a **literal** of the real ``complextasks/optimize-scale`` chaos entry (with
the harness placeholders already resolved) and asserts it validates through the
typed :class:`ChaosSpec` and discriminates to
:class:`GenerateLoadFault` / :class:`TimeTrigger` with the documented
``target.service_url`` / ``qps`` / ``delay_seconds`` values.

This is the gap CONVENTIONS §9 locks for every component — without it the typed
nodes can drift away from the only real spec in the repo. The literal mirrors
the verification component's regression test and keeps this test independent of
*when* the task file itself is migrated to native YAML (that migration, and the
end-to-end check against the real file, live with the harness PR).
"""

from __future__ import annotations

from devops_bench.chaos import ChaosSpec
from devops_bench.chaos.faults.generate_load import GenerateLoadFault
from devops_bench.chaos.triggers.time_delay import TimeTrigger

# The real optimize-scale chaos entry, native-YAML shape, with the harness
# placeholders ({{TARGET_DEPLOYMENT_NAME}} / {{NAMESPACE}}) resolved as the
# harness does at run time. ``verification`` is the legacy alias for ``verify``.
_OPTIMIZE_SCALE_CHAOS_ENTRY: dict = {
    "name": "Planned Load Spike",
    "trigger": {"type": "time", "delay_seconds": 5},
    "action": {
        "type": "generate_load",
        "target": {
            "service_url": "http://web-app.default.svc.cluster.local",
            "qps": 300,
        },
    },
    "verification": "Planned Load Spike Verification",
}


def test_optimize_scale_chaos_entry_parses_and_discriminates():
    spec = ChaosSpec.model_validate(_OPTIMIZE_SCALE_CHAOS_ENTRY)

    assert spec.name == "Planned Load Spike"
    # Trigger discriminates to the time-delay node and carries the authored delay.
    assert isinstance(spec.trigger, TimeTrigger)
    assert spec.trigger.type == "time"
    assert spec.trigger.delay_seconds == 5
    # Action discriminates to the generate-load fault with the resolved URL, the
    # authored qps, and no spurious defaults overriding it.
    assert isinstance(spec.action, GenerateLoadFault)
    assert spec.action.type == "generate_load"
    assert spec.action.target.service_url == "http://web-app.default.svc.cluster.local"
    assert spec.action.target.qps == 300
    # The legacy ``verification`` alias resolves into the canonical ``verify``
    # reference field — chaos never imports a verification node.
    assert spec.verify == "Planned Load Spike Verification"
