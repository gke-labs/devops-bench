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

"""Per-run isolation for the legacy evaluator so runs can execute concurrently.

Standalone counterpart to ``devops_bench.core.run_env`` for the legacy ``pkg/``
arm (the two arms share no code). When isolation is enabled (``--parallel`` /
``BENCH_PARALLEL``), each evaluator process gets its own ``KUBECONFIG``,
``CLOUDSDK_CONFIG``, and ``TF_DATA_DIR`` plus a run-unique, prefix-safe cluster
name, so multiple processes on one host (bastion or local) do not collide.
Isolation is opt-in to keep single-run and ``--no-infra`` workflows unchanged.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from dataclasses import dataclass

__all__ = ["RunEnv", "parallel_enabled"]

# GKE cluster names cap at 40 chars and must match ``[a-z]([-a-z0-9]*[a-z0-9])?``.
_MAX_CLUSTER_NAME = 40
# Run discriminator placed at the FRONT of derived cluster names so it survives
# the service-account ``account_id`` truncation (substr 0,10) in the tf/ stacks.
_CLUSTER_TOKEN_LEN = 8

_TRUE_VALUES = frozenset({"1", "true", "yes", "y", "on"})


def parallel_enabled() -> bool:
    """Return whether per-run isolation is requested via ``BENCH_PARALLEL``."""
    return os.environ.get("BENCH_PARALLEL", "").strip().lower() in _TRUE_VALUES


def _default_run_id() -> str:
    """Build a run id unique among concurrent processes on one host."""
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"


@dataclass(frozen=True)
class RunEnv:
    """Isolation context for one legacy evaluator process.

    Attributes:
        run_id: Stable identifier reused for artifact naming.
        isolated: Whether per-run isolation is active (inert pass-through when
            False).
        run_dir: Per-run scratch directory (created on :meth:`apply`).
        kubeconfig_path: Per-run ``KUBECONFIG`` target, or None.
        gcloud_config_path: Per-run ``CLOUDSDK_CONFIG`` target, or None.
        tf_data_dir: Per-run ``TF_DATA_DIR`` target, or None.
    """

    run_id: str
    isolated: bool
    run_dir: str
    kubeconfig_path: str | None
    gcloud_config_path: str | None
    tf_data_dir: str | None

    @classmethod
    def create(
        cls,
        *,
        parallel: bool,
        run_id: str | None = None,
        state_root: str | None = None,
    ) -> RunEnv:
        """Build a run environment, resolving the run id and scratch paths.

        Args:
            parallel: When True, derive per-run isolated paths; else an inert
                pass-through.
            run_id: Explicit run id; defaults to ``RUN_ID`` env, then a
                PID/timestamp id.
            state_root: Root for the scratch dir; defaults to
                ``BENCH_RUN_STATE_ROOT`` env, then ``<tmp>/devops-bench-runs``.

        Returns:
            The constructed :class:`RunEnv` (no side effects until :meth:`apply`).
        """
        resolved_id = run_id or os.environ.get("RUN_ID") or _default_run_id()
        if not parallel:
            return cls(resolved_id, False, os.getcwd(), None, None, None)

        root = state_root or os.environ.get("BENCH_RUN_STATE_ROOT") or os.path.join(
            tempfile.gettempdir(), "devops-bench-runs"
        )
        run_dir = os.path.join(root, resolved_id)
        return cls(
            run_id=resolved_id,
            isolated=True,
            run_dir=run_dir,
            kubeconfig_path=os.path.join(run_dir, "kubeconfig"),
            gcloud_config_path=os.path.join(run_dir, "gcloud"),
            tf_data_dir=os.path.join(run_dir, "tf-data"),
        )

    def apply(self) -> None:
        """Create the scratch dir and point process env at the per-run paths.

        A no-op when not isolated. Mutates ``os.environ`` so every subprocess
        (``gcloud`` / ``kubectl`` / ``tofu`` / agents) inherits the isolated
        kubeconfig, gcloud config, and tofu data dir.
        """
        if not self.isolated:
            return
        os.makedirs(self.gcloud_config_path, exist_ok=True)  # type: ignore[arg-type]
        os.makedirs(self.tf_data_dir, exist_ok=True)  # type: ignore[arg-type]
        os.environ["KUBECONFIG"] = self.kubeconfig_path  # type: ignore[assignment]
        os.environ["CLOUDSDK_CONFIG"] = self.gcloud_config_path  # type: ignore[assignment]
        os.environ["TF_DATA_DIR"] = self.tf_data_dir  # type: ignore[assignment]
        os.environ["RUN_ID"] = self.run_id
        os.environ["BENCH_RUN_DIR"] = self.run_dir

    @property
    def cluster_token(self) -> str:
        """Short, prefix-safe, DNS-label-safe discriminator from the run id."""
        digest = hashlib.blake2s(self.run_id.encode(), digest_size=8).hexdigest()
        return ("c" + digest)[:_CLUSTER_TOKEN_LEN]

    def cluster_name(self, base: str) -> str:
        """Derive a collision-free cluster name from ``base`` for this run.

        Returns ``base`` unchanged when not isolated; otherwise prepends the run
        token (so it survives SA-name truncation), clamped to the GKE 40-char
        limit with no trailing dash.

        Args:
            base: The configured (shared) cluster name.

        Returns:
            The per-run cluster name.
        """
        if not self.isolated:
            return base
        return f"{self.cluster_token}-{base}"[:_MAX_CLUSTER_NAME].rstrip("-")
