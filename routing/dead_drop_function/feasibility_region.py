"""
feasibility_region.py

Behavioral feasibility region abstraction (UPDATED).

This module defines the interface used by the deterministic dead-drop resolver
to enforce behavioral constraints learned from benign GitHub interaction traces.

Responsibilities:
- Represent precomputed, time-indexed behavioral feasibility constraints
- Answer whether a given (time, artifact class, role, URL) tuple is allowed
- (Optional) Provide a probability / score for allowed URLs, derived from benign traces

Non-responsibilities:
- No learning or inference (training)
- No snapshot access
- No identifier resolution
- No timing or scheduling logic
- No network or API access
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Literal, Optional

Role = Literal["sender", "receiver"]


# ============================================================
# Exceptions
# ============================================================

class FeasibilityViolation(Exception):
    """
    Raised when a candidate route violates the feasibility region.
    """
    pass


# ============================================================
# Feasibility Region Interface
# ============================================================

class FeasibilityRegion(ABC):
    """
    Abstract behavioral feasibility region R.

    R constrains which URLs may be accessed or mutated by which role at a given
    epoch t, based on empirically learned benign behavior.
    """

    # ---------------------------------------------------------
    # Core query interface (used by dead_drop_resolver)
    # ---------------------------------------------------------

    @abstractmethod
    def is_url_allowed(self, *, epoch: int, artifact_class: str, role: Role, url: str) -> bool:
        """
        Return True iff the given URL is behaviorally feasible for the role at the specified epoch.

        This method MUST be:
        - deterministic
        - side-effect free
        - constant-time w.r.t. snapshot size
        """
        raise NotImplementedError

    # ---------------------------------------------------------
    # Optional scoring interface (probabilistic modeling)
    # ---------------------------------------------------------

    def url_weight(self, *, epoch: int, artifact_class: str, role: Role, url: str) -> Optional[float]:
        """
        OPTIONAL.

        If implemented, returns a non-negative weight proportional to the empirical
        likelihood of observing this URL access under benign traces.

        Returning None means "no weight information"; resolver will fall back to
        uniform deterministic selection over allowed URLs.
        """
        return None

    # ---------------------------------------------------------
    # Convenience helper
    # ---------------------------------------------------------

    def filter_allowed_urls(self, *, epoch: int, artifact_class: str, role: Role, urls: Iterable[str]) -> list[str]:
        """
        Filter a candidate URL set down to those allowed by the feasibility region.
        """
        return [
            url
            for url in urls
            if self.is_url_allowed(epoch=epoch, artifact_class=artifact_class, role=role, url=url)
        ]
