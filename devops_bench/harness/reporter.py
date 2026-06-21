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

"""Result sink: write the per-run ``results.json`` and collect artifacts.

The harness depends on a :class:`ResultReporter` rather than calling
:func:`json.dump` inline, so output sinks (DB, dashboard, blob store) can be
added by substituting the reporter without editing the orchestrator.
"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any

from devops_bench.core import get_logger

__all__ = ["ResultReporter"]

_log = get_logger("harness.reporter")

_RESULTS_FILENAME = "results.json"


class ResultReporter:
    """Default reporter writing ``results.json`` to a timestamped run directory.

    Every value written through this reporter has already been routed through
    ``MetricScore.to_entry()`` / ``AgentResult.to_dict()`` /
    ``ChaosResult.model_dump()`` / ``VerificationResult.model_dump()`` by the
    orchestrator, so the reporter itself only knows how to JSON-encode the
    final dicts.

    Args:
        results_root: Root directory under which per-run subdirectories are
            created. Defaults to ``"results"``.
        run_dir_prefix: Prefix for the timestamped subdirectory name.
    """

    def __init__(
        self,
        results_root: str | os.PathLike[str] = "results",
        *,
        run_dir_prefix: str = "run_",
    ) -> None:
        self.results_root = Path(results_root)
        self.run_dir_prefix = run_dir_prefix

    def new_run_dir(self) -> Path:
        """Create and return a fresh timestamped run directory under the root.

        Returns:
            The absolute path of the newly created directory.
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = self.results_root / f"{self.run_dir_prefix}{timestamp}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def write(self, run_dir: str | os.PathLike[str], results: list[dict[str, Any]]) -> Path:
        """Write ``results`` to ``<run_dir>/results.json`` and return the path.

        Args:
            run_dir: Run directory previously returned by :meth:`new_run_dir`.
            results: Per-task result dicts already shaped to the on-disk schema.

        Returns:
            The path of the JSON file written.
        """
        path = Path(run_dir) / _RESULTS_FILENAME
        with open(path, "w") as f:
            json.dump(results, f, indent=2)
        _log.info("wrote results.json with %d entries to %s", len(results), path)
        return path
