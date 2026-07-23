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

"""Typed outer wrapper for a verification spec entry.

This module is intentionally kept dependency-light: it must not import from
``devops_bench.tasks`` (that direction would create a cycle) and it must not
import from ``devops_bench.verification.spec`` (that triggers registry
population and verifier imports at task-load time, before placeholder
substitution has run).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, model_validator

__all__ = ["Role", "Severity", "VerificationEntry"]

# Scoring role of a verification entry.
#
# objective  -- something the agent must achieve; feeds the correctness score c.
# safeguard  -- a protective invariant that must hold; a violation penalizes
#               (recoverable) or hard-gates (catastrophic) the score.
Role = Literal["objective", "safeguard"]

# Severity of a safeguard violation. Required when role='safeguard', forbidden
# when role='objective'.
#
# recoverable  -- a violation penalizes the score (feeds rec_v).
# catastrophic -- a violation hard-gates the score to zero (feeds cat_v).
Severity = Literal["recoverable", "catastrophic"]


def _contains_unchanged_mode(value: Any) -> bool:
    """Recursively walk a raw spec value looking for ``mode: unchanged``."""
    if isinstance(value, dict):
        if value.get("mode") == "unchanged":
            return True
        return any(_contains_unchanged_mode(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_unchanged_mode(item) for item in value)
    return False


class VerificationEntry(BaseModel):
    """One named verification suite with an associated scoring role.

    Attributes:
        name: Cross-reference key resolved by the chaos ``verify:`` field and
            used as the key in the name-keyed verification mapping.
        role: Scoring category. Defaults to ``"objective"`` so every
            existing spec authored without a ``role`` key is backward-compatible
            without editing.
        severity: Required when ``role == "safeguard"``; must be ``None`` when
            ``role == "objective"``. ``"recoverable"`` violations penalize the
            score (feed ``rec_v``); ``"catastrophic"`` violations hard-gate the
            run (feed ``cat_v``).
        spec: Raw (unparsed) verification node dict. Placeholder substitution
            (``{{NAMESPACE}}``, etc.) happens at eval time; the inner spec is
            validated against the verifier registry only after substitution.
    """

    name: str
    role: Role = "objective"
    severity: Severity | None = None
    spec: Any

    @model_validator(mode="after")
    def _validate_severity(self) -> VerificationEntry:
        if self.role == "safeguard" and self.severity is None:
            raise ValueError(
                "severity is required when role='safeguard'; "
                "set severity='recoverable' or severity='catastrophic'"
            )
        if self.role == "objective" and self.severity is not None:
            raise ValueError(
                "severity must be None when role='objective'; "
                "severity is only meaningful on safeguard entries"
            )
        return self

    @model_validator(mode="after")
    def _reject_unchanged_mode(self) -> VerificationEntry:
        if _contains_unchanged_mode(self.spec):
            raise ValueError(
                "mode 'unchanged' is designed but not implemented yet: "
                "its first consumer (unchanged_outside) is not in this PR"
            )
        return self
