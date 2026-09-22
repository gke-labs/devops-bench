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

"""Thin, shell-free wrappers around ``gcloud secrets`` for Secret Manager reads.

Reads only: nothing here mutates a secret. These back verification checks that
ask Secret Manager itself what a version's state or payload is, rather than
trusting a task's own report of what it did.
"""

from __future__ import annotations

import json
from typing import Any

from devops_bench.core import get_logger
from devops_bench.core.subprocess import run

__all__ = ["access_secret_version", "describe_secret_version"]

_log = get_logger("gcp.secretmanager")


def describe_secret_version(
    project_id: str, secret_id: str, version: str, *, timeout: float | None = None
) -> dict[str, Any]:
    """Fetch one secret version's metadata via ``gcloud secrets versions describe``.

    Args:
        project_id: GCP project the secret lives in.
        secret_id: Secret Manager secret id (not the full resource path).
        version: Version number, or ``"latest"``.
        timeout: Optional seconds before the subprocess is killed.

    Returns:
        The parsed JSON document. Its ``state`` field is one of ``ENABLED``,
        ``DISABLED``, or ``DESTROYED``.

    Raises:
        SubprocessError: If gcloud exits non-zero or times out.
        json.JSONDecodeError: If the output is not valid JSON.
    """
    completed = run(
        [
            "gcloud",
            "secrets",
            "versions",
            "describe",
            version,
            "--secret",
            secret_id,
            "--project",
            project_id,
            "--format",
            "json",
        ],
        timeout=timeout,
    )
    return json.loads(completed.stdout)


def access_secret_version(
    project_id: str, secret_id: str, version: str, *, timeout: float | None = None
) -> str:
    """Fetch one secret version's plaintext payload via ``gcloud secrets versions access``.

    Args:
        project_id: GCP project the secret lives in.
        secret_id: Secret Manager secret id (not the full resource path).
        version: Version number, or ``"latest"`` (the newest ``ENABLED``
            version, per Secret Manager's own alias resolution).
        timeout: Optional seconds before the subprocess is killed.

    Returns:
        The version's payload, stripped of a trailing newline.

    Raises:
        SubprocessError: If gcloud exits non-zero (e.g. the version is
            disabled or destroyed) or times out.
    """
    completed = run(
        [
            "gcloud",
            "secrets",
            "versions",
            "access",
            version,
            "--secret",
            secret_id,
            "--project",
            project_id,
        ],
        timeout=timeout,
    )
    return completed.stdout.strip()
