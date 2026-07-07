from abc import ABC, abstractmethod
from typing import Dict, List, Union, Optional
from pydantic import BaseModel

class VerificationResult(BaseModel):
    """Structured verification outcome report."""
    success: bool
    elapsed_time: float
    reason: str
    details: Optional[Union[Dict[str, 'VerificationResult'], List['VerificationResult'], dict]] = None

class BaseVerifier(BaseModel, ABC):
    """Base Pydantic class for all verification checks."""
    
    @abstractmethod
    def verify(self, timeout_sec: int) -> VerificationResult:
        """Performs the verification check and returns a structured VerificationResult."""
        pass
