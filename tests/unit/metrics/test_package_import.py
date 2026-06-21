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

"""Import policy for ``devops_bench.metrics`` and the provider-SDK guarantee.

Under the current policy "light init is a guideline, not a rule": importing
``devops_bench.metrics`` eagerly pulls ``deepeval`` (the single eval framework).
``deepeval`` itself imports the provider SDKs (``anthropic``/``google.genai``/
``openai``) at its own import time, so they ride along when metrics is imported
— that is accepted.

The provider-SDK *laziness* guarantee that still holds is in our own models
layer: ``import devops_bench.models`` must not construct a provider client, so
it pulls no SDK on its own (the SDK is imported only when a model is selected).
"""

from __future__ import annotations

import subprocess
import sys

_SDKS = ("anthropic", "google.genai", "google.generativeai", "openai", "ollama")


def _fresh_import(module: str) -> set[str]:
    """Import ``module`` in a fresh interpreter; return which SDKs it pulled."""
    code = (
        "import sys\n"
        f"import {module}  # noqa: F401\n"
        f"print([s for s in {_SDKS!r} if s in sys.modules])\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    return set(eval(proc.stdout.strip()))  # noqa: S307 - trusted child output


def test_metrics_exposes_public_symbols():
    code = (
        "import devops_bench.metrics as m\n"
        "assert hasattr(m, 'METRICS')\n"
        "assert hasattr(m, 'MetricScore')\n"
        "print('ok')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


def test_models_layer_stays_sdk_lazy():
    # The real optional-dependency guarantee: our models layer constructs no
    # provider client on import, so no SDK is pulled until a model is selected.
    assert _fresh_import("devops_bench.models") == set()
