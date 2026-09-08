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

"""Unit tests for devops_bench.gcp.secretmanager.

These patch the module-local ``run`` so no real ``gcloud`` is invoked, and
assert the exact argv lists.
"""

import subprocess

from devops_bench.gcp import secretmanager


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    """Build a real CompletedProcess for the patched ``run``."""
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout)


def test_describe_secret_version_builds_argv_and_parses_json(mocker):
    mock_run = mocker.patch(
        "devops_bench.gcp.secretmanager.run",
        return_value=_completed('{"name": "projects/p/secrets/s/versions/1", "state": "DISABLED"}'),
    )

    result = secretmanager.describe_secret_version("my-project", "my-secret", "1", timeout=5)

    assert result == {"name": "projects/p/secrets/s/versions/1", "state": "DISABLED"}
    assert mock_run.call_args.args[0] == [
        "gcloud",
        "secrets",
        "versions",
        "describe",
        "1",
        "--secret",
        "my-secret",
        "--project",
        "my-project",
        "--format",
        "json",
    ]
    assert mock_run.call_args.kwargs["timeout"] == 5


def test_access_secret_version_builds_argv_and_strips_output(mocker):
    mock_run = mocker.patch(
        "devops_bench.gcp.secretmanager.run",
        return_value=_completed("s3cr3t-value\n"),
    )

    result = secretmanager.access_secret_version("my-project", "my-secret", "latest")

    assert result == "s3cr3t-value"
    assert mock_run.call_args.args[0] == [
        "gcloud",
        "secrets",
        "versions",
        "access",
        "latest",
        "--secret",
        "my-secret",
        "--project",
        "my-project",
    ]
