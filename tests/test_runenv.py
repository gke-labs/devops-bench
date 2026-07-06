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

"""Unit tests for the legacy evaluator's per-run isolation helper."""

import os

from pkg.runenv import RunEnv, parallel_enabled


def test_parallel_enabled(monkeypatch):
    monkeypatch.delenv("BENCH_PARALLEL", raising=False)
    assert parallel_enabled() is False
    monkeypatch.setenv("BENCH_PARALLEL", "true")
    assert parallel_enabled() is True
    monkeypatch.setenv("BENCH_PARALLEL", "0")
    assert parallel_enabled() is False


def test_passthrough_when_not_parallel(monkeypatch):
    monkeypatch.delenv("KUBECONFIG", raising=False)
    monkeypatch.delenv("TF_DATA_DIR", raising=False)
    run_env = RunEnv.create(parallel=False, run_id="fixed")
    run_env.apply()
    assert run_env.isolated is False
    assert run_env.cluster_name("c") == "c"
    assert "KUBECONFIG" not in os.environ
    assert "TF_DATA_DIR" not in os.environ


def test_apply_sets_isolated_env_and_creates_dirs(monkeypatch, tmp_path):
    old_env = dict(os.environ)
    try:
        run_env = RunEnv.create(parallel=True, run_id="run-1", state_root=str(tmp_path))
        run_env.apply()
        expected = tmp_path / "run-1"
        assert os.environ["KUBECONFIG"] == str(expected / "kubeconfig")
        assert os.environ["CLOUDSDK_CONFIG"] == str(expected / "gcloud")
        assert os.environ["TF_DATA_DIR"] == str(expected / "tf-data")
        assert os.environ["RUN_ID"] == "run-1"
        assert os.environ["BENCH_RUN_DIR"] == str(expected)
        assert (expected / "gcloud").is_dir()
        assert (expected / "tf-data").is_dir()
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def test_cluster_name_prefixed_deterministic_and_unique(tmp_path):
    a = RunEnv.create(parallel=True, run_id="A", state_root=str(tmp_path))
    a2 = RunEnv.create(parallel=True, run_id="A", state_root=str(tmp_path))
    b = RunEnv.create(parallel=True, run_id="B", state_root=str(tmp_path))
    assert a.cluster_name("hpa") == a2.cluster_name("hpa")
    assert a.cluster_name("hpa") != b.cluster_name("hpa")
    assert a.cluster_name("hpa").startswith(a.cluster_token)
    # Token leads so it survives SA-name truncation at 10 chars.
    assert a.cluster_name("hpa")[:10] != b.cluster_name("hpa")[:10]


def test_cluster_name_respects_length_limit(tmp_path):
    name = RunEnv.create(parallel=True, run_id="X", state_root=str(tmp_path)).cluster_name("a" * 60)
    assert len(name) <= 40
    assert not name.endswith("-")
