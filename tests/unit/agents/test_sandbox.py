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

"""Unit tests for devops_bench.agents.sandbox: container naming and reaping."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from devops_bench.agents import sandbox
from devops_bench.core.errors import SubprocessError


def test_container_name_for_workspace_is_deterministic_and_prefixed() -> None:
    name = sandbox.container_name_for_workspace(Path("/tmp/workspace-abc123"))
    assert name == "devops-bench-agent-workspace-abc123"


def test_container_name_for_workspace_differs_per_workspace() -> None:
    a = sandbox.container_name_for_workspace(Path("/tmp/workspace-a"))
    b = sandbox.container_name_for_workspace(Path("/tmp/workspace-b"))
    assert a != b


def test_current_cluster_name_returns_none_for_non_kind_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(argv, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="gke_simrankaurk-gke-dev_us-central1-a_optscale-eval\n",
            stderr="",
        )

    monkeypatch.setattr(sandbox, "run", fake_run)
    assert sandbox.current_cluster_name() is None


def test_current_cluster_name_strips_kind_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sandbox,
        "run",
        lambda argv, **kwargs: SimpleNamespace(returncode=0, stdout="kind-my-cluster\n", stderr=""),
    )
    assert sandbox.current_cluster_name() == "my-cluster"


def test_uses_exec_credential_plugin_true_when_exec_block_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sandbox,
        "run",
        lambda argv, **kwargs: SimpleNamespace(
            returncode=0, stdout="map[apiVersion:client.authentication.k8s.io/v1beta1 ...]", stderr=""
        ),
    )
    assert sandbox.uses_exec_credential_plugin() is True


def test_uses_exec_credential_plugin_false_when_no_exec_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sandbox, "run", lambda argv, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr="")
    )
    assert sandbox.uses_exec_credential_plugin() is False


def test_wrap_argv_defaults_to_kind_network() -> None:
    argv = sandbox.wrap_argv(
        ["gemini", "-p", "hi"],
        workspace=Path("/tmp/ws"),
        kubeconfig=Path("/tmp/ws/kubeconfig"),
        image="agent-image",
    )
    assert "--network" in argv
    assert argv[argv.index("--network") + 1] == "kind"


def test_wrap_argv_omits_network_flag_when_network_is_none() -> None:
    argv = sandbox.wrap_argv(
        ["gemini", "-p", "hi"],
        workspace=Path("/tmp/ws"),
        kubeconfig=Path("/tmp/ws/kubeconfig"),
        image="agent-image",
        network=None,
    )
    assert "--network" not in argv


def test_wrap_argv_includes_name_flag_when_container_name_given() -> None:
    argv = sandbox.wrap_argv(
        ["gemini", "-p", "hi"],
        workspace=Path("/tmp/ws"),
        kubeconfig=Path("/tmp/ws/kubeconfig"),
        image="agent-image",
        container_name="devops-bench-agent-ws",
    )
    assert "--name" in argv
    assert argv[argv.index("--name") + 1] == "devops-bench-agent-ws"


def test_wrap_argv_omits_name_flag_when_none_given() -> None:
    argv = sandbox.wrap_argv(
        ["gemini", "-p", "hi"],
        workspace=Path("/tmp/ws"),
        kubeconfig=Path("/tmp/ws/kubeconfig"),
        image="agent-image",
    )
    assert "--name" not in argv


def test_kill_container_invokes_docker_kill_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return SimpleNamespace(returncode=0, stdout="devops-bench-agent-ws\n", stderr="")

    monkeypatch.setattr(sandbox, "run", fake_run)
    sandbox.kill_container("devops-bench-agent-ws")
    assert captured["argv"] == ["docker", "kill", "devops-bench-agent-ws"]


def test_kill_container_never_raises_when_docker_kill_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Killing an already-gone container (the common case, ``--rm`` beat us to
    it) must be a harmless no-op, not a crash."""

    def fake_run(argv, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="No such container")

    monkeypatch.setattr(sandbox, "run", fake_run)
    sandbox.kill_container("devops-bench-agent-gone")  # must not raise


def test_container_guard_kills_container_on_normal_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    killed: list[str] = []
    monkeypatch.setattr(sandbox, "kill_container", killed.append)

    with sandbox.container_guard("devops-bench-agent-ws"):
        pass

    assert killed == ["devops-bench-agent-ws"]


def test_container_guard_kills_container_on_exception_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crash inside the guarded block must still reap the container."""
    killed: list[str] = []
    monkeypatch.setattr(sandbox, "kill_container", killed.append)

    with (
        pytest.raises(RuntimeError, match="boom"),
        sandbox.container_guard("devops-bench-agent-ws"),
    ):
        raise RuntimeError("boom")

    assert killed == ["devops-bench-agent-ws"]


def test_container_guard_kills_container_on_timeout_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """A SubprocessError raised by a timed-out ``core.subprocess.run`` call
    inside the guarded block must still reap the container, exactly as the
    gemini_cli agent's own timeout handling relies on."""
    killed: list[str] = []
    monkeypatch.setattr(sandbox, "kill_container", killed.append)

    timeout_exc: SubprocessError | None = None
    with sandbox.container_guard("devops-bench-agent-ws"):
        try:
            raise SubprocessError(["docker", "run"], returncode=-1, stdout="partial", stderr="")
        except SubprocessError as exc:
            # Mirrors how the agent harness swallows the timeout inside the
            # guarded block rather than letting it propagate.
            timeout_exc = exc

    assert timeout_exc is not None
    assert killed == ["devops-bench-agent-ws"]


def test_sweep_stray_containers_kills_only_matching_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[:2] == ["docker", "ps"]:
            return SimpleNamespace(returncode=0, stdout="abc123\ndef456\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(sandbox, "run", fake_run)
    sandbox.sweep_stray_containers()

    list_call = calls[0]
    assert list_call[0:2] == ["docker", "ps"]
    assert any("devops-bench-agent-" in arg for arg in list_call)
    kill_calls = [c for c in calls if c[:2] == ["docker", "kill"]]
    assert kill_calls == [["docker", "kill", "abc123"], ["docker", "kill", "def456"]]


def test_sweep_stray_containers_handles_docker_ps_failure_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(argv, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="docker daemon not running")

    monkeypatch.setattr(sandbox, "run", fake_run)
    sandbox.sweep_stray_containers()  # must not raise


def _exec_plugin_dispatch(
    *, sa_exists: bool, sa_token: str | None = "sa-token", admin_token: str | None = None
):
    """A fake ``run`` dispatching on argv shape, for exec-plugin build_agent_kubeconfig tests."""

    def fake_run(argv, **kwargs):
        if argv[-1] == "jsonpath={.clusters[0].cluster.certificate-authority-data}":
            return SimpleNamespace(returncode=0, stdout="ZmFrZS1jYQ==", stderr="")
        if argv[-1] == "jsonpath={.users[0].user.exec}":
            return SimpleNamespace(returncode=0, stdout="map[command:some-cloud-auth-plugin]", stderr="")
        if argv[-1] == "jsonpath={.clusters[0].cluster.server}":
            return SimpleNamespace(returncode=0, stdout="https://34.1.2.3", stderr="")
        if argv[:5] == ["kubectl", "-n", sandbox.AGENT_SA_NAMESPACE, "get", "sa"]:
            return SimpleNamespace(returncode=0 if sa_exists else 1, stdout="", stderr="")
        if argv[:5] == ["kubectl", "-n", sandbox.AGENT_SA_NAMESPACE, "create", "token"]:
            return SimpleNamespace(returncode=0, stdout=sa_token or "", stderr="")
        if argv == ["some-cloud", "print-access-token"]:
            return SimpleNamespace(returncode=0, stdout=admin_token or "", stderr="")
        raise AssertionError(f"unexpected argv in exec-plugin kubeconfig test: {argv}")

    return fake_run


def test_build_agent_kubeconfig_exec_plugin_with_seeded_service_account_uses_its_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        sandbox, "run", _exec_plugin_dispatch(sa_exists=True, sa_token="scoped-token\n")
    )
    path = sandbox.build_agent_kubeconfig(None, tmp_path)
    assert path is not None
    text = path.read_text()
    assert "https://34.1.2.3" in text
    assert "token: scoped-token" in text


def test_build_agent_kubeconfig_exec_plugin_without_service_account_mints_admin_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(sandbox.ADMIN_TOKEN_CMD_ENV, "some-cloud print-access-token")
    monkeypatch.setattr(
        sandbox, "run", _exec_plugin_dispatch(sa_exists=False, admin_token="ya29.admin-token\n")
    )
    path = sandbox.build_agent_kubeconfig(None, tmp_path)
    assert path is not None
    text = path.read_text()
    assert "https://34.1.2.3" in text
    assert "token: ya29.admin-token" in text


def test_build_agent_kubeconfig_exec_plugin_refuses_without_service_account_or_admin_token_cmd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(sandbox.ADMIN_TOKEN_CMD_ENV, raising=False)
    monkeypatch.setattr(sandbox, "run", _exec_plugin_dispatch(sa_exists=False))
    assert sandbox.build_agent_kubeconfig(None, tmp_path) is None


def test_build_agent_kubeconfig_refuses_when_context_is_neither_kind_nor_exec_plugin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(argv, **kwargs):
        if argv[-1] == "jsonpath={.clusters[0].cluster.certificate-authority-data}":
            return SimpleNamespace(returncode=0, stdout="ZmFrZS1jYQ==", stderr="")
        if argv[-1] == "jsonpath={.users[0].user.exec}":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected argv: {argv}")

    monkeypatch.setattr(sandbox, "run", fake_run)
    assert sandbox.build_agent_kubeconfig(None, tmp_path) is None


def test_sweep_stray_containers_is_a_noop_when_none_are_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(sandbox, "run", fake_run)
    sandbox.sweep_stray_containers()

    kill_calls = [c for c in calls if c[:2] == ["docker", "kill"]]
    assert kill_calls == []
