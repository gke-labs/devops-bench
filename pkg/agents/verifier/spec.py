from pydantic import RootModel

from pkg.agents.verifier.pod_healthy import PodHealthyVerifier
from pkg.agents.verifier.scaling_complete import ScalingCompleteVerifier

# SingleVerificationSpec is a discriminated union of all supported checker types
SingleVerificationSpec = PodHealthyVerifier | ScalingCompleteVerifier


# Top-level VerificationSpec which can parse a dict, a list, or a single checker spec.
class VerificationSpec(
    RootModel[
        dict[str, SingleVerificationSpec] | list[SingleVerificationSpec] | SingleVerificationSpec
    ]
):
    """Represents a structured verification specification."""

    pass
