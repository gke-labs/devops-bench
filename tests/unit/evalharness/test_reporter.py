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

"""Golden tests for the preserved ``results.json`` schema (Decision D3).

Two invariants are pinned here:

1. **The ``ResultReporter`` writes the input list verbatim.** The reporter is
   a thin sink the engine depends on (``harness-refactor-handoff.md`` §8);
   it must not reshape the payload.
2. **Success and failed records carry the *same* top-level key set.** A
   downstream parser iterating one shape can never ``KeyError`` crossing
   into the other. The tests drive the production code path by invoking
   :meth:`DefaultEvalHarness._build_success_record` /
   :meth:`DefaultEvalHarness._build_failed_record` on a stub
   :class:`AgentResult` and asserting ``set(record.keys()) == required_keys``.
   A hand-rolled dict would let the builders drift silently — these tests
   intentionally exercise the real builders.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devops_bench.agents.result import AgentResult, ToolCall
from devops_bench.evalharness.default import DefaultEvalHarness
from devops_bench.evalharness.reporter import ResultReporter
from devops_bench.tasks import Task

# Pinned legacy + symmetric-union key set. Every key listed here must be
# present on *both* the success record and the failed record (Decision D3).
# A reader iterating one shape may rely on every key being present on the
# other — the previous schema asymmetry that motivated this fix is gone.
_RESULTS_JSON_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "input",
        "output",
        "latency",
        "tokens",
        "tools",
        "trajectory",
        "skills",
        "name",
        "folder",
        "status",
        "error",
        "errors",
        "scores",
        "expected_output",
        "expected_output_raw",
        "retrieval_context",
        "chaos_spec",
        "verification_spec",
        "chaos_report",
        "perf_report",
        "documentation",
        "capabilities_granted",
        "verification_parse_errors",
        "generation_only",
        "validated",
    }
)


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every ``BENCH_*`` / ``AGENT_*`` knob the harness reads.

    Keeps the test deterministic — without it the developer's shell env
    could grant skills or MCP that the golden assertions don't expect.
    """
    for var in (
        "BENCH_USE_MCP",
        "BENCH_AGENT_TYPE",
        "AGENT_MCP_SERVER",
        "AGENT_ALLOWED_TOOLS",
        "AGENT_SKILLS_PATHS",
        "AGENT_RULES_TEXT",
        "AGENT_TARGET",
        "AGENT_MODEL",
        "AGENT_PROVIDER",
    ):
        monkeypatch.delenv(var, raising=False)


def _stub_task() -> Task:
    """Build a typed task with a few non-trivial fields the records carry."""
    return Task.from_dict(
        {
            "task_id": "demo-1",
            "name": "demo",
            "prompt": "do the thing",
            "expected_output": "exp",
            "retrieval_context": ["doc-a"],
            "chaos_spec": {"chaos": "yes"},
            "verification_spec": {"verify": "yes"},
        }
    )


def _stub_agent_result() -> AgentResult:
    """Build an agent result with output, trajectory, tokens, latency populated."""
    return AgentResult(
        output="done",
        trajectory=[
            ToolCall(
                name="run_command",
                args={"command": "kubectl get pods"},
                result="pod/web-app Running",
                status="completed",
            ).to_dict()
        ],
        tokens={"input": 10, "output": 5},
        latency=1.5,
    )


def test_reporter_writes_results_json_with_indented_payload(tmp_path: Path) -> None:
    """The reporter writes ``results.json`` under the run dir with the input list."""
    reporter = ResultReporter(results_root=tmp_path)
    run_dir = reporter.new_run_dir()
    payload = [{"name": "demo", "status": "success"}]

    written = reporter.write(run_dir, payload)

    assert written == run_dir / "results.json"
    on_disk = json.loads(written.read_text())
    assert on_disk == payload


def test_reporter_writes_rows_json(tmp_path: Path) -> None:
    """``write_rows`` writes the flattened rows to ``rows.json`` verbatim."""
    reporter = ResultReporter(results_root=tmp_path)
    run_dir = reporter.new_run_dir()
    rows = [{"setupId": "m-h", "taskName": "demo", "outcomeScore": 0.9}]

    written = reporter.write_rows(run_dir, rows)

    assert written == run_dir / "rows.json"
    assert json.loads(written.read_text()) == rows


def test_reporter_writes_manifest_json(tmp_path: Path) -> None:
    """``write_manifest`` writes the run-level manifest to ``manifest.json``."""
    reporter = ResultReporter(results_root=tmp_path)
    run_dir = reporter.new_run_dir()
    manifest = {"runId": run_dir.name, "model": "m", "augmentation": ["mcp"]}

    written = reporter.write_manifest(run_dir, manifest)

    assert written == run_dir / "manifest.json"
    assert json.loads(written.read_text()) == manifest


def test_write_run_artifacts_emits_rows_and_manifest(
    isolated_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The harness flattens scored records into rows.json + manifest.json.

    Drives the real ``_write_run_artifacts`` path so the bridge between the
    harness records and the dashboard ``ResultRow`` contract is exercised
    end-to-end: capabilities → augmentation, nested ``scores`` → flat
    ``outcomeScore``, provider tokens → flat ``inputTokens``.
    """
    monkeypatch.setenv("AGENT_MODEL", "alpha-pro")
    reporter = ResultReporter(results_root=tmp_path)
    harness = DefaultEvalHarness(
        project_id="p", cluster_name="c", agent_type="gemini", reporter=reporter
    )
    run_dir = reporter.new_run_dir()
    records = [
        {
            "name": "Rotate Secret",
            "folder": "task_001",
            "status": "success",
            "latency": 12.0,
            "tokens": {"input": 100, "output": 20},
            "scores": {
                "OutcomeValidity": {"score": 0.9, "success": True, "reason": "ok"},
                "ToolInvocation": {"score": 0.6, "success": True, "reason": "ok"},
            },
        }
    ]

    harness._write_run_artifacts(run_dir, records)  # noqa: SLF001 - testing internals

    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["model"] == "alpha-pro"
    assert manifest["harness"] == "gemini"
    # use_mcp defaults True (get_bool) and no skills granted -> ["mcp"].
    assert manifest["augmentation"] == ["mcp"]
    assert manifest["setupId"] == "alpha-pro-gemini-mcp"
    assert manifest["runId"] == run_dir.name

    rows = json.loads((run_dir / "rows.json").read_text())
    assert len(rows) == 1
    row = rows[0]
    assert row["taskFolder"] == "task_001"
    assert row["taskName"] == "Rotate Secret"
    assert row["outcomeScore"] == 0.9
    assert row["toolScore"] == 0.6
    assert row["inputTokens"] == 100
    assert row["outputTokens"] == 20
    assert row["iteration"] == 0
    assert row["setupId"] == manifest["setupId"]


def test_new_run_dir_returns_unique_path_under_root(tmp_path: Path) -> None:
    """Two reporters sharing a root produce directories underneath it."""
    reporter = ResultReporter(results_root=tmp_path)
    a = reporter.new_run_dir()
    assert a.parent == tmp_path
    assert a.name.startswith("run_")


def test_new_run_dir_records_last_run_dir(tmp_path: Path) -> None:
    """``new_run_dir`` exposes the most recent dir via ``last_run_dir``."""
    r = ResultReporter(results_root=tmp_path)
    assert r.last_run_dir is None
    d = r.new_run_dir()
    assert r.last_run_dir == d


def test_new_run_dir_appends_run_id(tmp_path: Path) -> None:
    """A supplied run id is appended so concurrent runs do not collide."""
    r = ResultReporter(results_root=tmp_path, run_id="20260101-120000-4242")
    d = r.new_run_dir()
    assert d.name.startswith("run_")
    assert d.name.endswith("_20260101-120000-4242")


def test_new_run_dir_sanitizes_run_id(tmp_path: Path) -> None:
    """Filesystem-unsafe characters in the run id are replaced."""
    r = ResultReporter(results_root=tmp_path, run_id="a/b c:d")
    d = r.new_run_dir()
    assert "/" not in d.name[len("run_") :]
    assert d.name.endswith("_a-b-c-d")


def test_legacy_success_record_keys_are_emitted_verbatim(
    isolated_env: None,
) -> None:
    """A real ``_build_success_record`` invocation matches the golden key set.

    The test drives the production code path — earlier versions asserted a
    hand-rolled dict, which let the builder drift away from the golden
    schema undetected. Today the key set is asserted on the actual output.
    """
    harness = DefaultEvalHarness(project_id="p", cluster_name="c")
    task = _stub_task()
    agent_res = _stub_agent_result()

    record = harness._build_success_record(  # noqa: SLF001 - testing internals
        task=task,
        prompt="resolved prompt",
        expected_output="resolved expected",
        agent_res=agent_res,
        chaos_report={"status": "success"},
        perf_report={"uptime_percentage": 100.0},
    )

    # Exact key equality — no drift in either direction.
    assert set(record.keys()) == _RESULTS_JSON_REQUIRED_KEYS
    # Spot-check the success-specific values.
    assert record["status"] == "success"
    assert record["output"] == "done"
    assert record["trajectory"][0]["name"] == "run_command"
    assert record["tokens"] == {"input": 10, "output": 5}
    # The error/errors slots are present but empty on a clean success run.
    assert record["error"] is None
    assert record["errors"] == []
    # Pre-scoring, ``scores`` is the empty dict; ``_score`` writes into it.
    assert record["scores"] == {}
    # Capabilities snapshot rides on every record (CONVENTIONS.md §7 closure).
    assert record["capabilities_granted"]["use_mcp"] is True  # default get_bool
    assert record["capabilities_granted"]["skills"] == []


def test_legacy_failed_record_keys_are_emitted_verbatim(
    isolated_env: None,
) -> None:
    """A real ``_build_failed_record`` invocation matches the SAME golden set.

    This is the BLOCKING D3 fix: success and failed records used to carry
    different key sets (success: ``errors`` + ``scores``; failed: ``error``
    + ``score``), so a parser iterating one would ``KeyError`` on the
    other. The symmetric union pinned here removes that asymmetry.
    """
    harness = DefaultEvalHarness(project_id="p", cluster_name="c")
    task = _stub_task()
    exc = RuntimeError("deployer.up() failed")

    record = harness._build_failed_record(task, exc)  # noqa: SLF001

    # Exact key equality — IDENTICAL to the success golden set.
    assert set(record.keys()) == _RESULTS_JSON_REQUIRED_KEYS
    # Failed-specific values.
    assert record["status"] == "failed"
    assert record["error"] == "deployer.up() failed"
    assert record["errors"] == ["deployer.up() failed"]
    assert record["scores"] == {}
    assert record["output"] == ""
    assert record["trajectory"] == []
    # Capabilities snapshot rides on failed records too, so dashboards
    # always see what the harness granted, even on a crash.
    assert "use_mcp" in record["capabilities_granted"]


def test_success_and_failed_records_have_identical_top_level_keys(
    isolated_env: None,
) -> None:
    """Direct invariant: ``set(success.keys()) == set(failed.keys())``.

    Reviewer-requested explicit assertion — the previous schema mismatch
    (success had ``errors``+``scores``; failed had ``error``+``score``) is
    pinned away here so a future change has to break this test to
    re-introduce the asymmetry.
    """
    harness = DefaultEvalHarness(project_id="p", cluster_name="c")
    task = _stub_task()

    success = harness._build_success_record(  # noqa: SLF001
        task=task,
        prompt="p",
        expected_output="e",
        agent_res=_stub_agent_result(),
        chaos_report={},
        perf_report={},
    )
    failed = harness._build_failed_record(task, RuntimeError("boom"))  # noqa: SLF001

    assert set(success.keys()) == set(failed.keys())
    # And both equal the pinned golden union.
    assert set(success.keys()) == _RESULTS_JSON_REQUIRED_KEYS


def test_record_keys_class_constant_matches_golden(isolated_env: None) -> None:
    """The harness's :attr:`_RECORD_KEYS` constant is the authoritative source.

    Pinning it here means a future contributor who adds a record field
    (and updates ``_RECORD_KEYS`` + both builders) must also update the
    golden constant in this test file — a single coordinated edit catches
    drift in either direction.
    """
    assert DefaultEvalHarness._RECORD_KEYS == _RESULTS_JSON_REQUIRED_KEYS  # noqa: SLF001


def test_verification_parse_errors_flow_into_success_record(
    isolated_env: None,
) -> None:
    """Verification-spec parse failures land on ``verification_parse_errors``."""
    harness = DefaultEvalHarness(project_id="p", cluster_name="c")
    record = harness._build_success_record(  # noqa: SLF001
        task=_stub_task(),
        prompt="p",
        expected_output="e",
        agent_res=_stub_agent_result(),
        chaos_report={},
        perf_report={},
        verification_parse_errors=[
            {"name": "broken", "reason": "missing type discriminator"}
        ],
    )
    assert record["verification_parse_errors"] == [
        {"name": "broken", "reason": "missing type discriminator"}
    ]


def test_verification_parse_errors_flow_into_failed_record(
    isolated_env: None,
) -> None:
    """The same plumbing exists on the failed path.

    A verification authoring failure must never be lost to a deployer
    crash — the operator should see both on the failed record.
    """
    harness = DefaultEvalHarness(project_id="p", cluster_name="c")
    record = harness._build_failed_record(  # noqa: SLF001
        _stub_task(),
        RuntimeError("boom"),
        verification_parse_errors=[{"name": "broken", "reason": "bad type"}],
    )
    assert record["verification_parse_errors"] == [
        {"name": "broken", "reason": "bad type"}
    ]


def test_record_carries_generation_only_and_validated(isolated_env: None) -> None:
    """``generation_only`` tracks ``deployer: noop``; ``validated`` rides from the task."""
    harness = DefaultEvalHarness(project_id="p", cluster_name="c")
    noop_task = Task.from_dict(
        {
            "task_id": "n",
            "name": "noop",
            "infrastructure": {"deployer": "noop"},
            "validated": True,
        }
    )
    tofu_task = Task.from_dict(
        {
            "task_id": "t",
            "name": "tofu",
            "infrastructure": {"deployer": "tofu", "stack": "prebuilt/minimum"},
        }
    )
    noop_rec = harness._empty_record(noop_task)  # noqa: SLF001 - testing internals
    tofu_rec = harness._empty_record(tofu_task)  # noqa: SLF001 - testing internals
    assert noop_rec["generation_only"] is True
    assert tofu_rec["generation_only"] is False
    assert noop_rec["validated"] is True
    assert tofu_rec["validated"] is False


def _vetted_task() -> Task:
    """A vetted (``validated: true``) task for run-level gating tests."""
    return Task.from_dict({"task_id": "v", "name": "vetted", "validated": True})


def test_success_record_validated_requires_clean_run(isolated_env: None) -> None:
    """A vetted task promotes only when the run had no error and ran tools."""
    harness = DefaultEvalHarness(project_id="p", cluster_name="c")
    record = harness._build_success_record(  # noqa: SLF001 - testing internals
        task=_vetted_task(),
        prompt="p",
        expected_output="e",
        agent_res=_stub_agent_result(),
        chaos_report={},
        perf_report={},
    )
    assert record["validated"] is True


def test_success_record_validated_false_on_errored_run(isolated_env: None) -> None:
    """An errored run (429 / timeout) on a vetted task must not promote.

    ``AgentResult.errored`` yields an empty trajectory + populated ``errors``
    while the record still reads ``status:"success"``; the run-level gate must
    reject it.
    """
    harness = DefaultEvalHarness(project_id="p", cluster_name="c")
    record = harness._build_success_record(  # noqa: SLF001 - testing internals
        task=_vetted_task(),
        prompt="p",
        expected_output="e",
        agent_res=AgentResult.errored("429 RESOURCE_EXHAUSTED"),
        chaos_report={},
        perf_report={},
    )
    assert record["status"] == "success"
    assert record["errors"]
    assert record["validated"] is False


def test_success_record_validated_false_on_empty_trajectory(isolated_env: None) -> None:
    """A vetted task with no recorded tool calls does not promote."""
    harness = DefaultEvalHarness(project_id="p", cluster_name="c")
    record = harness._build_success_record(  # noqa: SLF001 - testing internals
        task=_vetted_task(),
        prompt="p",
        expected_output="e",
        agent_res=AgentResult(output="text only", trajectory=[]),
        chaos_report={},
        perf_report={},
    )
    assert record["validated"] is False


def test_failed_record_never_validated(isolated_env: None) -> None:
    """A failed run never promotes, even on a vetted task."""
    harness = DefaultEvalHarness(project_id="p", cluster_name="c")
    record = harness._build_failed_record(  # noqa: SLF001 - testing internals
        _vetted_task(), RuntimeError("boom")
    )
    assert record["validated"] is False
