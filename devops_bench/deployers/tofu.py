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

"""OpenTofu-backed deployer driving repo-local ``tf/`` stacks."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from devops_bench.core import ClusterInfo, ConfigError, get_logger
from devops_bench.core.subprocess import run
from devops_bench.deployers.base import Deployer

if TYPE_CHECKING:
    from devops_bench.providers import Provider

__all__ = ["TFDeployer"]

# This module lives at ``<repo_root>/devops_bench/deployers/tofu.py``; the repo
# root is therefore three levels up, and Tofu stacks live under ``<repo_root>/tf``.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_TF_ROOT = _REPO_ROOT / "tf"

_log = get_logger("deployers.tofu")


def _format_var(value: Any) -> str:
    """Format a Python value as an OpenTofu ``-var`` literal.

    Args:
        value: Variable value to serialize.

    Returns:
        ``"true"``/``"false"`` for booleans, JSON for lists and dicts,
        ``"null"`` for ``None``, and ``str(value)`` otherwise.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    if value is None:
        return "null"
    return str(value)


class TFDeployer(Deployer):
    """Deployer that provisions a cluster via an OpenTofu stack.

    A pure provisioning engine: it runs ``tofu`` and delegates all cloud-specific
    behavior (account credentials, cluster credentials, project resolution) to
    its :class:`~devops_bench.providers.Provider`. Honors the ``TF_DATA_DIR``
    environment variable so OpenTofu state can be redirected for idempotent runs.

    Path resolution: a relative ``tf_dir`` is resolved under ``<repo_root>/tf``;
    an absolute path (``~`` is expanded) is used as-is, so stacks may live outside
    the repository.

    Args:
        tf_dir: Stack directory; an absolute/``~`` path used as-is, or a name
            resolved under ``<repo_root>/tf``.
        provider: Cloud provider supplying credentials and cluster details.
        variables: OpenTofu input variables passed as ``-var`` flags.

    Raises:
        ConfigError: If the stack directory does not exist.
    """

    def __init__(
        self,
        tf_dir: str,
        provider: Provider,
        variables: dict[str, Any] | None = None,
    ) -> None:
        tf_path = Path(tf_dir).expanduser()
        if tf_path.is_absolute():
            if not tf_path.exists():
                raise ConfigError(f"Absolute TF directory not found: {tf_dir}")
            self.tf_dir = str(tf_path)
        else:
            repo_tf_path = _TF_ROOT / tf_path
            if not repo_tf_path.exists():
                raise ConfigError(f"TF stack not found in repo: {tf_dir} (checked {repo_tf_path})")
            self.tf_dir = str(repo_tf_path)

        self.provider = provider
        self.variables = variables or {}

    def _var_flags(self) -> list[str]:
        flags: list[str] = []
        for key, value in self.variables.items():
            flags.extend(["-var", f"{key}={_format_var(value)}"])
        return flags

    @staticmethod
    def _state_flags() -> list[str]:
        """Return ``-state`` flags redirecting state into ``TF_DATA_DIR``.

        When ``TF_DATA_DIR`` is set (the parallel-isolation path keys it to a
        per-run dir), the local state file is placed alongside it so concurrent
        runs of the same stack do not share or corrupt ``terraform.tfstate`` and
        its lock. Returns an empty list when ``TF_DATA_DIR`` is unset, so a
        single run keeps OpenTofu's default in-directory state.
        """
        tf_data_dir = os.environ.get("TF_DATA_DIR")
        if not tf_data_dir or not tf_data_dir.strip():
            return []
        return ["-state", str(Path(tf_data_dir) / "terraform.tfstate")]

    def up(self) -> None:
        tf_path = Path(self.tf_dir)
        if not tf_path.exists():
            raise ConfigError(f"TF directory not found: {self.tf_dir}")

        self.provider.ensure_account_credentials()
        run(["tofu", "init", "-input=false"], cwd=self.tf_dir, capture=False)

        cmd = [
            "tofu",
            "apply",
            "-auto-approve",
            "-input=false",
            *self._state_flags(),
            *self._var_flags(),
        ]
        run(cmd, cwd=self.tf_dir, capture=False)

    def down(self) -> None:
        tf_path = Path(self.tf_dir)
        if not tf_path.exists():
            _log.warning("TF directory %s not found. Skipping teardown.", self.tf_dir)
            return

        self.provider.ensure_account_credentials()
        run(["tofu", "init", "-input=false"], cwd=self.tf_dir, capture=False)

        cmd = [
            "tofu",
            "destroy",
            "-auto-approve",
            "-input=false",
            *self._state_flags(),
            *self._var_flags(),
        ]
        run(cmd, cwd=self.tf_dir, capture=False)

    def get_cluster_info(self) -> ClusterInfo:
        """Read cluster details from the stack outputs.

        Parses the stack outputs (no side effects) and delegates project
        resolution and kubeconfig setup to the provider.

        Returns:
            The provisioned cluster's :class:`~devops_bench.core.ClusterInfo`.

        Raises:
            ConfigError: If required outputs are missing or unparseable.
        """
        run(["tofu", "init", "-input=false"], cwd=self.tf_dir, capture=False)

        result = run(
            ["tofu", "output", "-json", *self._state_flags()],
            cwd=self.tf_dir,
            capture=True,
        )
        try:
            outputs = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ConfigError("failed to parse 'tofu output -json'") from exc

        cluster_name = outputs.get("cluster_name", {}).get("value")
        if not cluster_name:
            raise ConfigError("Failed to retrieve 'cluster_name' from TF outputs.")

        location = outputs.get("cluster_location", {}).get("value")
        if not location:
            raise ConfigError("Failed to retrieve 'cluster_location' from TF outputs.")

        return self.provider.ensure_cluster_credentials(cluster_name, location, self.variables)
