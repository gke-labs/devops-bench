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

"""Thin argparse CLI wrapping :func:`devops_bench.run.run_benchmark`.

The library entrypoint owns all real work; this module only parses flags into a
:class:`~devops_bench.run.BenchmarkConfig` and maps the outcome to an exit code.
``run`` imports stay function-local so ``import devops_bench.cli`` stays light.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from devops_bench.core import ConfigError

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from devops_bench.run import BenchmarkConfig


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``devops-bench`` console script.

    Returns:
        A configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="devops-bench",
        description="Run the DevOps-bench evaluation pipeline over a task source.",
    )
    parser.add_argument(
        "source",
        help="Tasks directory or task spec file (.yaml / .yml / .json).",
    )
    parser.add_argument("--project", dest="project_id", default=None, help="GCP project id.")
    parser.add_argument("--cluster", dest="cluster_name", default=None, help="GKE cluster name.")
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N tasks.")
    parser.add_argument("--results-root", default=None, help="Root directory for run artifacts.")
    parser.add_argument("--agent-type", default=None, help="Override BENCH_AGENT_TYPE.")
    parser.add_argument("--judge-provider", default=None, help="Override JUDGE_PROVIDER.")
    parser.add_argument("--judge-model", default=None, help="Override JUDGE_MODEL.")
    # Tri-state (default None) so a flag can override the env in either
    # direction; store_true could only ever turn these on, never back off.
    parser.add_argument(
        "--no-infra",
        dest="no_infra",
        action="store_const",
        const=True,
        default=None,
        help="Skip infrastructure provisioning (no project/cluster required).",
    )
    parser.add_argument(
        "--infra",
        dest="no_infra",
        action="store_const",
        const=False,
        help="Force infrastructure provisioning even if BENCH_NO_INFRA is set.",
    )
    parser.add_argument(
        "--no-teardown",
        dest="no_teardown",
        action="store_const",
        const=True,
        default=None,
        help="Skip teardown of provisioned infrastructure.",
    )
    parser.add_argument(
        "--teardown",
        dest="no_teardown",
        action="store_const",
        const=False,
        help="Force teardown even if BENCH_NO_TEARDOWN is set.",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help=(
            "Isolate this run (own kubeconfig / gcloud config / tofu data dir and "
            "a run-unique cluster name) so it can run concurrently with others."
        ),
    )
    parser.add_argument(
        "--run-id",
        dest="run_id",
        default=None,
        help="Explicit run id for isolation/artifact naming (default: RUN_ID env or generated).",
    )
    return parser


def args_to_config(args: argparse.Namespace) -> BenchmarkConfig:
    """Merge parsed CLI args over an env-resolved base config.

    Flags that were provided override the env base; unset flags fall back to env.

    Args:
        args: Parsed namespace from :func:`build_parser`.

    Returns:
        The merged :class:`~devops_bench.run.BenchmarkConfig`.
    """
    from devops_bench.run import BenchmarkConfig

    base = BenchmarkConfig.from_env(args.source)

    overrides: dict[str, object] = {}
    for field in (
        "project_id",
        "cluster_name",
        "limit",
        "results_root",
        "agent_type",
        "judge_provider",
        "judge_model",
        "run_id",
    ):
        value = getattr(args, field)
        if value is not None:
            overrides[field] = value

    return replace(
        base,
        **overrides,
        no_infra=args.no_infra if args.no_infra is not None else base.no_infra,
        no_teardown=(args.no_teardown if args.no_teardown is not None else base.no_teardown),
        parallel=args.parallel or base.parallel,
    )


def _fmt_reason(reason: Any, limit: int = 160) -> str:
    """Flatten a possibly-multiline reason to a single truncated line."""
    if not reason:
        return ""
    flat = " ".join(str(reason).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def print_run_summary(records: list[dict[str, Any]]) -> None:
    """Print a per-task deterministic + judge scoreboard to stdout.

    Consolidates the deterministic verification rollup (which otherwise only
    reaches ``results.json``) with the LLM-judge scores, so a single run's
    outcome is legible without opening the JSON.
    """
    if not records:
        return
    print("\n================ run summary ================")
    for r in records:
        print(f"\n{r.get('name') or '<unknown>'}  [{r.get('status') or ''}]")

        rollup = r.get("verification_rollup")
        if rollup is not None:
            c = rollup.get("c")
            rec_v = rollup.get("rec_v")
            c_s = "n/a" if c is None else f"{c:.2f}"
            rec_s = "n/a" if rec_v is None else f"{rec_v:.2f}"
            print(f"  deterministic:  c={c_s}  rec_v={rec_s}  cat_v={rollup.get('cat_v')}")

        entries = r.get("verification_entries_report") or []
        objectives = [e for e in entries if e.get("role") == "objective"]
        safeguards = [e for e in entries if e.get("role") == "safeguard"]
        if objectives:
            print("  objectives (feed c):")
            for e in objectives:
                mark = "PASS" if e.get("success") else "FAIL"
                tail = "" if e.get("success") else f"  {_fmt_reason(e.get('reason'))}"
                print(f"    [{mark}] {e.get('name')} (w{e.get('weight')}){tail}")
        if safeguards:
            print("  safeguards:")
            for e in safeguards:
                held = e.get("success")
                mark = "HELD  " if held else "BREACH"
                tail = "" if held else f"  {_fmt_reason(e.get('reason'))}"
                print(f"    [{mark}] {e.get('name')} ({e.get('severity')}){tail}")

        scores = r.get("scores") or {}
        if scores:
            print("  judge (GEval, non-gating):")
            for metric, val in scores.items():
                if isinstance(val, dict):
                    score = val.get("score")
                    score_s = "n/a" if score is None else f"{score:.2f}"
                    mark = "PASS" if val.get("success") else "FAIL"
                    print(f"    [{mark}] {metric} = {score_s}  {_fmt_reason(val.get('reason'))}")
                else:
                    print(f"    {metric} = {val}")


def main(argv: list[str] | None = None) -> int:
    """Console entry point: parse args, run the benchmark, return an exit code.

    Args:
        argv: Argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        ``0`` if no task failed, ``1`` if at least one failed, ``2`` on
        configuration error.
    """
    from devops_bench.run import run_benchmark

    parser = build_parser()
    args = parser.parse_args(argv)
    config = args_to_config(args)

    try:
        result = run_benchmark(config)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print_run_summary(result.results)
    failed = sum(1 for r in result.results if r.get("status") == "failed")
    print(f"ran {len(result.results)} task(s), {failed} failed; results: {result.results_path}")
    return 1 if failed else 0
