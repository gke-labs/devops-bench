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

"""Run a CLI agent inside a container with a scoped cluster identity.

WHY THIS EXISTS. The CLI agent harnesses invoke the agent binary as a plain
subprocess inheriting the parent environment, so ``run_shell_command`` under
``--approval-mode yolo`` has the operator's entire filesystem. Observed in real
runs: an agent read another task's ``seed.sh`` and ``verify.sh``, searched the
home directory for its own fixtures by namespace name, and copied an unrelated
archive out of ``~/Downloads`` before running ``rm -rf``. The agent's own
workspace sandbox does not help, because it only guards the native file tools
and not the shell.

Two boundaries, and they solve different problems:

* The CONTAINER removes the host filesystem and the operator's environment. That
  closes the on-disk answer-key channel and the safety hazard.
* The SCOPED TOKEN decides what the agent may do to the cluster. That is task
  design, not containment: it makes the agent's identity part of the topology.

Neither closes the third channel. An agent that can read a cluster can read
anything a task put IN that cluster, and a task that needs the agent to inspect a
workload cannot use RBAC to hide that workload's own definition. Answer material
must not be seeded into the cluster in the first place; see the factory's
``answer-leakage.md``.
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

from devops_bench.core import get_logger
from devops_bench.core.subprocess import run

__all__ = [
    "sandbox_enabled",
    "current_cluster_name",
    "uses_exec_credential_plugin",
    "build_agent_kubeconfig",
    "discover_fixture_mounts",
    "wrap_argv",
    "container_name_for_workspace",
    "kill_container",
    "container_guard",
    "sweep_stray_containers",
]

_log = get_logger("agents.sandbox")

# The ServiceAccount a task may seed to declare what its agent is allowed to do.
# Absent, the agent falls back to the operator's own context, which is what the
# harness did unconditionally before this module existed.
AGENT_SA_NAME = os.environ.get("BENCH_AGENT_SA", "bench-agent")
AGENT_SA_NAMESPACE = os.environ.get("BENCH_AGENT_SA_NAMESPACE", "bench-system")
TOKEN_DURATION = os.environ.get("BENCH_AGENT_TOKEN_DURATION", "2h")

# Every sandboxed container this harness starts carries this name prefix,
# followed by its run workspace's own directory name (see
# ``container_name_for_workspace``). The prefix is what lets
# ``sweep_stray_containers`` find and reap containers this harness itself
# created, and only those: a name match is the entire authorization to kill
# something, so it must never be able to match a container this harness did
# not start.
_CONTAINER_NAME_PREFIX = "devops-bench-agent-"


def sandbox_enabled() -> bool:
    """True when the agent should run containerised.

    Opt-in rather than default so it can be A/B'd against the current behaviour
    while tasks are still being debugged.
    """
    return os.environ.get("BENCH_AGENT_SANDBOX", "").strip().lower() in {"docker", "1", "true"}


def current_cluster_name() -> str | None:
    """Derive the kind cluster name from the active kubectl context.

    The agent harness is handed a workspace and a prompt, never the cluster name,
    so rather than widen that interface we recover it from the context kind wrote:
    ``kind-<cluster>``. That is also exactly the prefix of the control-plane
    container name the container needs to reach, so the two stay consistent by
    construction. Returns None for a non-kind context (not an error on its own:
    see :func:`uses_exec_credential_plugin` for the other shape this sandbox
    understands).
    """
    ctx = run(["kubectl", "config", "current-context"], check=False).stdout or ""
    ctx = ctx.strip()
    if not ctx.startswith("kind-"):
        return None
    return ctx[len("kind-") :]


def uses_exec_credential_plugin() -> bool:
    """True when the active context authenticates via an exec credential plugin.

    Deliberately provider-agnostic: this asks a structural question about the
    current kubeconfig (does its ``user`` entry shell out to a plugin, e.g. a
    cloud vendor's own ``kubectl`` credential helper, rather than carry a static
    client certificate?), not "which cloud is this." Any such plugin is
    unusable inside the sandboxed container (it is not installed there, and
    would need ambient cloud credentials the container deliberately lacks), so
    :func:`build_agent_kubeconfig` cannot reuse the operator's own user block
    the way it does for a static client cert and must mint a bearer token
    instead (see its non-kind branch). Which command mints that token is not
    this module's concern either — see ``BENCH_SANDBOX_ADMIN_TOKEN_CMD`` there.
    """
    result = run(
        ["kubectl", "config", "view", "--raw", "--minify", "-o", "jsonpath={.users[0].user.exec}"],
        check=False,
    )
    return bool((result.stdout or "").strip())


def _kubectl_json(*args: str) -> dict:
    completed = run(["kubectl", *args, "-o", "json"], check=False)
    if completed.returncode != 0:
        return {}
    try:
        return json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return {}


# A caller outside this package sets this (see e.g. the GCP provider's
# `ensure_cluster_credentials`) to whatever shell command mints a fresh bearer
# token for the current cloud identity, when the current context authenticates
# via an exec credential plugin this sandbox cannot run itself (see
# :func:`uses_exec_credential_plugin`) and the task seeded no agent
# ServiceAccount to fall back to. Kept as an env-sourced command rather than a
# literal here so this module never has to name a specific cloud vendor.
ADMIN_TOKEN_CMD_ENV = "BENCH_SANDBOX_ADMIN_TOKEN_CMD"


def build_agent_kubeconfig(cluster_name: str | None, dest_dir: Path) -> Path | None:
    """Write a kubeconfig the container can use, and return its path.

    Two things have to change from the operator's own kubeconfig:

    1. The SERVER. ``kind`` writes ``https://127.0.0.1:<port>``, which means
       nothing inside a container. ``kind`` also creates a Docker network named
       ``kind``, so a container joined to it reaches the API server at
       ``https://<cluster>-control-plane:6443``. The API server certificate
       covers the control-plane node name, so TLS still verifies and no
       ``--insecure-skip-tls-verify`` is needed. A cloud-managed cluster's own
       server URL (a real, publicly routable IP or DNS name) already means
       something from inside a container, so it is reused as-is instead.
    2. The CREDENTIAL. The operator's context authenticates as cluster-admin —
       kind via a client certificate, a cloud-managed cluster typically via an
       exec credential plugin (which needs an ambient cloud CLI/credential
       install the sandbox deliberately lacks, so the container can't run it
       itself). If the task seeded an agent ServiceAccount we mint a
       short-lived token for it instead, so the agent holds exactly the
       permissions the task chose to give it — this part is identical
       regardless of cluster kind. If it did not, we fall back to an
       admin-equivalent credential and say so loudly, because that is a
       strictly larger grant than most tasks intend: kind's own client cert, or
       for an exec-plugin context a bearer token minted by whatever command
       :data:`ADMIN_TOKEN_CMD_ENV` names (set by the provider that knows how,
       e.g. the same cloud identity Terraform's own ``kubernetes`` provider
       already used to manage the cluster, so it is already proven to hold
       real access — not a new grant).

    Args:
        cluster_name: The kind cluster name (see :func:`current_cluster_name`),
            or ``None`` for a non-kind context — an exec-credential-plugin
            context (:func:`uses_exec_credential_plugin`) is the only other
            shape this understands.

    Returns None when no kubeconfig could be built, in which case the caller
    should refuse to run rather than silently fall back to the host.
    """
    ca = run(
        [
            "kubectl",
            "config",
            "view",
            "--raw",
            "--minify",
            "-o",
            "jsonpath={.clusters[0].cluster.certificate-authority-data}",
        ],
        check=False,
    ).stdout
    if not ca:
        _log.error("could not read cluster CA from the current context; refusing to sandbox")
        return None

    exec_plugin_context = cluster_name is None and uses_exec_credential_plugin()
    if cluster_name is not None:
        server = f"https://{cluster_name}-control-plane:6443"
    elif exec_plugin_context:
        server = (
            run(
                [
                    "kubectl",
                    "config",
                    "view",
                    "--raw",
                    "--minify",
                    "-o",
                    "jsonpath={.clusters[0].cluster.server}",
                ],
                check=False,
            ).stdout
            or ""
        ).strip()
        if not server:
            _log.error("could not read the cluster's server URL from the current context")
            return None
    else:
        _log.error(
            "current context is neither kind nor an exec-credential-plugin context; "
            "this sandbox's networking assumptions do not apply"
        )
        return None

    sa_exists = (
        run(
            ["kubectl", "-n", AGENT_SA_NAMESPACE, "get", "sa", AGENT_SA_NAME],
            check=False,
        ).returncode
        == 0
    )

    if sa_exists:
        token = run(
            [
                "kubectl",
                "-n",
                AGENT_SA_NAMESPACE,
                "create",
                "token",
                AGENT_SA_NAME,
                f"--duration={TOKEN_DURATION}",
            ],
            check=False,
        ).stdout
        if not token:
            _log.error(
                "ServiceAccount %s/%s exists but token minting failed",
                AGENT_SA_NAMESPACE,
                AGENT_SA_NAME,
            )
            return None
        user_block = f"user: {{token: {token.strip()}}}"
        _log.info(
            "agent identity: ServiceAccount %s/%s (scoped by the task)",
            AGENT_SA_NAMESPACE,
            AGENT_SA_NAME,
        )
    elif cluster_name is not None:
        # No task-declared identity. Reuse the operator's client cert. This is
        # cluster-admin on kind, so the container boundary is doing all the work
        # and the RBAC boundary is doing none.
        cert = run(
            [
                "kubectl",
                "config",
                "view",
                "--raw",
                "--minify",
                "-o",
                "jsonpath={.users[0].user.client-certificate-data}",
            ],
            check=False,
        ).stdout
        key = run(
            [
                "kubectl",
                "config",
                "view",
                "--raw",
                "--minify",
                "-o",
                "jsonpath={.users[0].user.client-key-data}",
            ],
            check=False,
        ).stdout
        if not (cert and key):
            _log.error("no agent ServiceAccount and no client cert in the current context")
            return None
        user_block = f"user: {{client-certificate-data: {cert}, client-key-data: {key}}}"
        _log.warning(
            "no ServiceAccount %s/%s: agent runs with the operator's admin credential. "
            "Seed one in the task's stack to scope it.",
            AGENT_SA_NAMESPACE,
            AGENT_SA_NAME,
        )
    else:
        # An exec-plugin context has no client cert in a modern kubeconfig (the
        # exec plugin is the only user entry); mint a bearer token via whatever
        # command the provider layer configured instead.
        admin_token_cmd = os.environ.get(ADMIN_TOKEN_CMD_ENV, "").strip()
        token = (
            run(shlex.split(admin_token_cmd), check=False).stdout if admin_token_cmd else None
        ) or ""
        token = token.strip()
        if not token:
            _log.error(
                "no agent ServiceAccount and no %s configured to mint a fallback token",
                ADMIN_TOKEN_CMD_ENV,
            )
            return None
        user_block = f"user: {{token: {token}}}"
        _log.warning(
            "no ServiceAccount %s/%s: agent runs with the operator's identity via a minted "
            "access token. Seed one in the task's stack to scope it.",
            AGENT_SA_NAMESPACE,
            AGENT_SA_NAME,
        )

    path = dest_dir / "kubeconfig"
    path.write_text(
        "apiVersion: v1\n"
        "kind: Config\n"
        f"clusters: [{{name: c, cluster: {{server: {server}, certificate-authority-data: {ca}}}}}]\n"
        f"users: [{{name: u, {user_block}}}]\n"
        "contexts: [{name: ctx, context: {cluster: c, user: u}}]\n"
        "current-context: ctx\n"
    )
    path.chmod(0o600)
    return path


# Env override naming this run's fixtures explicitly, as ``:``-separated host
# paths. Set it for a stack whose fixture name does not carry the cluster token
# that :func:`discover_fixture_mounts` keys off.
FIXTURES_ENV = "BENCH_AGENT_FIXTURES"


def discover_fixture_mounts(cluster_name: str | None) -> dict[str, str]:
    """Find this run's seeded task fixtures and map them into the container.

    A task's stack seeds its inputs next to the operator's home — a GitOps repo
    (``~/opa-repo-<cluster>.git``), a delivered advisory, a rightsizing report —
    and the prompt then points the agent at ``~/<name>``. The container
    repoints ``HOME`` at ``/workspace`` and mounts neither the real home nor the
    repository, so before this the agent was told to read a file that could not
    exist for it. That is not containment, it is a broken task: the fixture is
    task INPUT, not answer material.

    It is also a containment problem in its own right. Observed across 40
    sandboxed runs on two models: every agent spent turns hunting the
    filesystem for the missing fixture, and the ones that hunted hardest
    escalated to a privileged pod, mounted the node's host disk, and reached
    the bench checkout — reading ``task.yaml`` and its ``verification_spec``.
    Giving the agent the input it was promised removes the reason to go looking.

    Eligibility is deliberately narrow: only paths whose NAME carries the
    run-unique ``cluster_name`` token match, and only at the top level of the
    home directory. So this can surface artifacts this run's own stack created
    and nothing else — not the operator's unrelated files, and not a concurrent
    run's fixtures.

    Args:
        cluster_name: The run's cluster name, used as the discriminating token.

    Returns:
        Host path -> container path, for :func:`wrap_argv`'s ``fixture_mounts``.
        Empty when nothing matches, which is the normal case for the many tasks
        that seed no files at all.
    """
    explicit = os.environ.get(FIXTURES_ENV, "").strip()
    if explicit:
        candidates = [Path(p).expanduser() for p in explicit.split(":") if p.strip()]
    elif not cluster_name:
        return {}
    else:
        home = Path.home()
        if not home.is_dir():
            return {}
        # Top level only, and the name must carry the token. A recursive walk
        # would widen this well past "artifacts of this run".
        candidates = sorted(home.glob(f"*{cluster_name}*"))

    mounts: dict[str, str] = {}
    for path in candidates:
        if not path.exists():
            _log.warning("declared fixture %s does not exist; not mounting it", path)
            continue
        # HOME is /workspace in the container, so a prompt's ``~/<name>``
        # resolves to exactly this path.
        mounts[str(path.resolve())] = f"/workspace/{path.name}"
    if mounts:
        _log.info("mounting %d task fixture(s): %s", len(mounts), sorted(mounts))
    return mounts


def wrap_argv(
    argv: list[str],
    *,
    workspace: Path,
    kubeconfig: Path,
    image: str | None = None,
    extra_env: dict[str, str] | None = None,
    container_name: str | None = None,
    network: str | None = "kind",
    fixture_mounts: dict[str, str] | None = None,
) -> list[str]:
    """Wrap an agent command line in ``docker run``.

    The mount set is deliberately short, and what is ABSENT matters more than
    what is present:

    * the repository is not mounted, so task definitions, seed scripts and
      scoring rubrics are unreachable
    * ``$HOME`` is not mounted, and HOME is repointed inside the container so a
      bare ``~`` cannot resolve to the operator's profile
    * the Docker socket is not mounted; with it the container boundary would be
      decorative, and it is tempting precisely because the cluster is Docker-hosted
    * Application Default Credentials are not mounted. Model access should use a
      credential scoped to model access; ADC is the operator's whole cloud identity
      and is a larger grant than the filesystem access this wrapper removes.

    Args:
        container_name: When given, passed as ``--name``, giving the running
            container a deterministic identity a caller can reap by name (see
            :func:`container_guard` / :func:`sweep_stray_containers`) even
            after the local ``docker run`` client process is gone. Normally
            :func:`container_name_for_workspace` derived from ``workspace``.
        network: Docker network to join. Defaults to ``"kind"`` (kind's own
            network, needed to reach ``<cluster>-control-plane`` by name — see
            :func:`build_agent_kubeconfig`). Pass ``None`` for a GKE-backed
            kubeconfig: GKE's server is a real, publicly routable address that
            already means something on the default bridge network, and there
            is no ``kind`` network to join outside a kind-provisioned host.
        fixture_mounts: Task fixtures, host path -> container path, mounted
            READ-WRITE (see :func:`discover_fixture_mounts`). The write bit is
            deliberate: several tasks ask the agent to commit its fix back to
            the seeded GitOps repo, so a read-only bind fails them as surely
            as no bind at all. This is the one mount set that is task INPUT
            rather than tooling, and it is kept separate from everything above
            precisely so that stays visible at the call site.
    """
    image = image or os.environ.get("BENCH_AGENT_IMAGE", "")
    if not image:
        raise ValueError("BENCH_AGENT_IMAGE must name an image containing the agent CLI")

    # Only the caller's resolved overlay crosses the boundary. Deliberately NOT
    # scraping os.environ for well-known credential names: that would reinstate
    # "inherit whatever the operator happened to export", which is the behaviour
    # this wrapper exists to remove. If a credential is not in the resolved
    # config, the agent does not get it.
    env_flags: list[str] = []
    for key, value in (extra_env or {}).items():
        env_flags += ["-e", f"{key}={value}"]

    name_flags = ["--name", container_name] if container_name else []
    network_flags = ["--network", network] if network else []

    fixture_flags: list[str] = []
    for host_path, container_path in (fixture_mounts or {}).items():
        fixture_flags += ["-v", f"{host_path}:{container_path}"]

    return [
        # No -i. Keeping stdin open gives the agent an open, non-TTY stdin to block
        # on, and a headless `-p <prompt>` run never reads it. Combined with
        # stdin=DEVNULL in core.subprocess this closes the channel at both ends.
        "docker",
        "run",
        "--rm",
        *name_flags,
        *network_flags,
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-v",
        f"{workspace}:/workspace",
        "-v",
        f"{kubeconfig}:/kubeconfig:ro",
        *fixture_flags,
        "-e",
        "KUBECONFIG=/kubeconfig",
        "-e",
        "HOME=/workspace",
        "-w",
        "/workspace",
        *env_flags,
        image,
        *argv,
    ]


def container_name_for_workspace(workspace: Path) -> str:
    """Deterministic ``docker run --name`` for one run's sandboxed agent.

    Ties the container 1:1 to the run's own workspace directory name (already
    unique per run: it comes from ``mint_dir(...)`` / ``TemporaryDirectory``),
    so a reaper can find and kill a stray container purely from its name,
    without threading a separate run id through the agent harness.
    """
    return f"{_CONTAINER_NAME_PREFIX}{workspace.name}"


def kill_container(name: str) -> None:
    """Best-effort ``docker kill`` by name. Never raises.

    ``--rm`` only removes a container once *the container's own process*
    exits; a ``docker run`` client killed out from under it (which is exactly
    what happens when ``core.subprocess.run`` hits its timeout and SIGKILLs
    the local wrapper process) leaves the container itself running in the
    daemon, unaffected, silently burning whatever quota the agent inside it
    is still spending. This is what actually stops it, independent of what
    happened to the local ``docker run`` process. A container that is already
    gone (the common case, when the agent exited cleanly and ``--rm`` already
    reaped it) fails harmlessly.
    """
    result = run(["docker", "kill", name], check=False)
    if result.returncode == 0:
        _log.info("reaped sandbox container %s", name)


@contextlib.contextmanager
def container_guard(name: str) -> Iterator[None]:
    """Guarantee :func:`kill_container` runs on every exit path.

    Wrap the ``docker run`` invocation in this so a normal return, an
    exception, and a timeout (which ``core.subprocess.run`` turns into a
    ``SubprocessError``) all still reap the container by name. ``--rm``
    already handles the graceful-exit case on its own; this closes every
    other one.
    """
    try:
        yield
    finally:
        kill_container(name)


def sweep_stray_containers() -> None:
    """Best-effort reap of containers this harness left running from a prior run.

    Intended to run once at harness start (before any run's own container
    exists) so a container orphaned by a prior crash or a killed harness
    process gets cleaned up before it burns any more quota. Matches
    exclusively on :data:`_CONTAINER_NAME_PREFIX`, this harness's own naming
    convention, so it can never reap a container it did not itself create.
    """
    listed = run(
        ["docker", "ps", "-q", "--filter", f"name=^{_CONTAINER_NAME_PREFIX}"],
        check=False,
    )
    if listed.returncode != 0:
        return
    stray_ids = [line.strip() for line in (listed.stdout or "").splitlines() if line.strip()]
    for container_id in stray_ids:
        result = run(["docker", "kill", container_id], check=False)
        if result.returncode == 0:
            _log.warning(
                "reaped stray sandbox container %s left running from a prior run", container_id
            )


def make_workspace() -> Path:
    """A world-writable scratch dir the container's non-root user can write to."""
    path = Path(tempfile.mkdtemp(prefix="devops-bench-sandbox-"))
    path.chmod(0o777)
    return path


def cleanup(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
