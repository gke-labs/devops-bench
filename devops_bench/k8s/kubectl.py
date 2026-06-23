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

"""Thin, shell-free wrappers around the ``kubectl`` command line."""

from __future__ import annotations

import json
from typing import Any, Protocol

from devops_bench.core.subprocess import CompletedProcess, run

__all__ = [
    "apply",
    "get_json",
    "rollout_status",
    "scale",
    "wait",
]


class KubeconfigProvider(Protocol):
    """Structural type for objects that expose a kubeconfig path."""

    kubeconfig_path: str | None


# Accepts a raw kubeconfig path or any object exposing ``kubeconfig_path``.
type KubeconfigSource = str | KubeconfigProvider | None


def _resolve_kubeconfig(kubeconfig: KubeconfigSource) -> str | None:
    """Return a kubeconfig path from a string or a provider object.

    Args:
        kubeconfig: Explicit path, a ``KubeconfigProvider``, or None.

    Returns:
        The kubeconfig path, or None when none is available.
    """
    if kubeconfig is None or isinstance(kubeconfig, str):
        return kubeconfig
    return kubeconfig.kubeconfig_path


def _namespace_args(namespace: str | None) -> list[str]:
    return ["-n", namespace] if namespace else []


def _selector_args(selector: str | None) -> list[str]:
    return ["-l", selector] if selector else []


def _run_kubectl(argv: list[str], kubeconfig: KubeconfigSource, **kwargs: Any) -> CompletedProcess:
    """Run ``kubectl`` with the resolved kubeconfig overlaid on the environment.

    Args:
        argv: Full kubectl command and arguments, never a shell string.
        kubeconfig: Explicit path, a ``KubeconfigProvider``, or None.
        **kwargs: Extra keyword arguments forwarded to ``core.subprocess.run``
            (e.g. ``timeout``).

    Returns:
        The completed process.

    Raises:
        SubprocessError: If kubectl exits non-zero or times out.
    """
    path = _resolve_kubeconfig(kubeconfig)
    extra_env = {"KUBECONFIG": path} if path else None
    return run(argv, extra_env=extra_env, **kwargs)


def wait(
    resource_type: str,
    *,
    selector: str | None = None,
    for_condition: str = "condition=Ready",
    timeout_sec: float,
    namespace: str | None = None,
    kubeconfig: KubeconfigSource = None,
) -> CompletedProcess:
    """Block until a resource satisfies a condition via ``kubectl wait``.

    Args:
        resource_type: Resource kind to wait on, e.g. ``"pod"``.
        selector: Optional label selector (``-l``).
        for_condition: Condition expression for ``--for``.
        timeout_sec: Maximum seconds to wait (``--timeout=<n>s``).
        namespace: Optional namespace (``-n``).
        kubeconfig: Kubeconfig path or context-like object.

    Returns:
        The completed process.

    Raises:
        SubprocessError: If the condition is not met before the timeout.
    """
    argv = [
        "kubectl",
        "wait",
        f"--for={for_condition}",
        resource_type,
        *_selector_args(selector),
        f"--timeout={timeout_sec}s",
        *_namespace_args(namespace),
    ]
    return _run_kubectl(argv, kubeconfig)


def get_json(
    resource_type: str,
    name: str | None = None,
    *,
    selector: str | None = None,
    namespace: str | None = None,
    kubeconfig: KubeconfigSource = None,
) -> dict[str, Any]:
    """Fetch a resource (or list) as parsed JSON via ``kubectl get -o json``.

    Args:
        resource_type: Resource kind to fetch, e.g. ``"pods"``.
        name: Optional specific resource name.
        selector: Optional label selector (``-l``).
        namespace: Optional namespace (``-n``).
        kubeconfig: Kubeconfig path or context-like object.

    Returns:
        The parsed JSON document.

    Raises:
        SubprocessError: If kubectl exits non-zero or times out.
        json.JSONDecodeError: If the output is not valid JSON.
    """
    argv = [
        "kubectl",
        "get",
        resource_type,
        *([name] if name else []),
        *_selector_args(selector),
        "-o",
        "json",
        *_namespace_args(namespace),
    ]
    completed = _run_kubectl(argv, kubeconfig)
    return json.loads(completed.stdout)


def apply(
    path: str,
    *,
    namespace: str | None = None,
    kubeconfig: KubeconfigSource = None,
) -> CompletedProcess:
    """Apply a manifest file or directory via ``kubectl apply -f``.

    Args:
        path: Manifest file, directory, or URL passed to ``-f``.
        namespace: Optional namespace (``-n``).
        kubeconfig: Kubeconfig path or context-like object.

    Returns:
        The completed process.

    Raises:
        SubprocessError: If kubectl exits non-zero or times out.
    """
    argv = ["kubectl", "apply", "-f", path, *_namespace_args(namespace)]
    return _run_kubectl(argv, kubeconfig)


def scale(
    resource: str,
    replicas: int,
    *,
    namespace: str | None = None,
    kubeconfig: KubeconfigSource = None,
) -> CompletedProcess:
    """Set the replica count of a resource via ``kubectl scale``.

    Args:
        resource: Resource reference, e.g. ``"deployment/web"``.
        replicas: Desired replica count.
        namespace: Optional namespace (``-n``).
        kubeconfig: Kubeconfig path or context-like object.

    Returns:
        The completed process.

    Raises:
        SubprocessError: If kubectl exits non-zero or times out.
    """
    argv = ["kubectl", "scale", f"--replicas={replicas}", resource, *_namespace_args(namespace)]
    return _run_kubectl(argv, kubeconfig)


def rollout_status(
    resource: str,
    *,
    timeout_sec: float | None = None,
    namespace: str | None = None,
    kubeconfig: KubeconfigSource = None,
) -> CompletedProcess:
    """Wait for a rollout to finish via ``kubectl rollout status``.

    Args:
        resource: Resource reference, e.g. ``"deployment/web"``.
        timeout_sec: Optional maximum seconds to wait (``--timeout=<n>s``).
        namespace: Optional namespace (``-n``).
        kubeconfig: Kubeconfig path or context-like object.

    Returns:
        The completed process.

    Raises:
        SubprocessError: If the rollout does not complete before the timeout.
    """
    argv = [
        "kubectl",
        "rollout",
        "status",
        resource,
        *([f"--timeout={timeout_sec}s"] if timeout_sec is not None else []),
        *_namespace_args(namespace),
    ]
    return _run_kubectl(argv, kubeconfig)
