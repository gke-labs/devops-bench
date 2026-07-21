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

"""Type-safe verification engine for validating cluster state.

This package exposes the verification spec model (:class:`VerificationSpec`
plus the combinators :class:`SequenceSpec`, :class:`ParallelSpec`,
:class:`AllSpec`, :class:`AnySpec`, :class:`NoneSpec`), its typed outcome
(:class:`VerificationResult`), the registry-driven extension surface
(:data:`VERIFIERS`, :func:`parse_node`), the :class:`VerifierAgent` that
evaluates specs (with per-entry converge/assert/hold modes via
:meth:`VerifierAgent.run_entry`), and the :func:`rollup` scoring over evaluated
entries. Importing the package pulls no heavy SDKs; concrete leaf verifiers
register via this package's submodules only.
"""

from devops_bench.verification.base import VERIFIERS, BaseVerifier, VerificationResult
from devops_bench.verification.rollup import (
    EvaluatedEntry,
    Role,
    RollupScores,
    Severity,
    rollup,
)
from devops_bench.verification.runner import VerifierAgent
from devops_bench.verification.spec import (
    AllSpec,
    AnySpec,
    NoneSpec,
    ParallelSpec,
    SequenceSpec,
    VerificationNode,
    VerificationSpec,
    json_schema,
    parse_node,
)

__all__ = [
    "AllSpec",
    "AnySpec",
    "BaseVerifier",
    "EvaluatedEntry",
    "NoneSpec",
    "ParallelSpec",
    "Role",
    "RollupScores",
    "SequenceSpec",
    "Severity",
    "VERIFIERS",
    "VerificationNode",
    "VerificationResult",
    "VerificationSpec",
    "VerifierAgent",
    "json_schema",
    "parse_node",
    "rollup",
]
