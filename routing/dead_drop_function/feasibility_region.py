"""
feasibility_region.py

Behavioral feasibility region abstraction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Literal, Optional

Role = Literal["sender", "receiver"]


class FeasibilityViolation(Exception):
    """Raised when a candidate route violates the feasibility region."""
    pass


class FeasibilityRegion(ABC):
    """Abstract behavioral feasibility region R."""

    @abstractmethod
    def is_url_allowed(self, *, epoch: int, artifact_class: str, role: Role, url: str) -> bool:
        """Return True iff the URL is behaviorally feasible."""
        raise NotImplementedError

    def url_weight(self, *, epoch: int, artifact_class: str, role: Role, url: str) -> Optional[float]:
        """Optional: return non-negative weight proportional to empirical likelihood."""
        return None

    def filter_allowed_urls(self, *, epoch: int, artifact_class: str, role: Role, urls: Iterable[str]) -> list[str]:
        """Filter a candidate URL set down to those allowed."""
        return [url for url in urls if self.is_url_allowed(epoch=epoch, artifact_class=artifact_class, role=role, url=url)]