"""
trace_weighted_feasibility.py  (FIXED)

Pure URL-level feasibility region for DeployStega.

This module enforces HARD behavioral constraints and answers ONLY the question:
    "Is this exact URL behaviorally feasible for this role at this epoch?"

CRITICAL MODEL GUARANTEES:
- Feasibility is binary (allowed / forbidden)
- Feasibility is URL-level, not artifact-level
- No probabilities, weights, or ranking
- No artifact-class selection
- No identifier selection
- No sampling logic
- Epochs may legitimately have zero feasible URLs

This module intentionally does NOT:
- choose artifact classes
- choose identifiers
- bias selection
- encode payloads
- perform probabilistic modeling

Any probabilistic behavior modeling MUST live outside the feasibility region.
"""

from __future__ import annotations

from typing import Dict, Iterable, Literal, Set

from .feasibility_region import FeasibilityRegion, Role


class URLAllowListFeasibilityRegion(FeasibilityRegion):
    """
    URL-level feasibility region based on an explicit allow-list.

    Feasibility is defined as membership in a precomputed allow-set:
        (artifact_class, role, epoch) -> set(URL)

    If a URL is not explicitly listed for the given epoch and role,
    it is infeasible by definition.
    """

    def __init__(
        self,
        *,
        allowlist: Dict[
            str,                    # artifact_class
            Dict[
                Role,               # sender | receiver
                Dict[
                    int,            # epoch bucket
                    Iterable[str],  # exact GitHub URLs
                ],
            ],
        ],
    ):
        self._allowlist: Dict[str, Dict[Role, Dict[int, Set[str]]]] = {}

        # Normalize eagerly into sets for O(1) membership checks
        for artifact_class, role_map in allowlist.items():
            self._allowlist.setdefault(artifact_class, {})
            for role, epoch_map in role_map.items():
                self._allowlist[artifact_class].setdefault(role, {})
                for epoch, urls in epoch_map.items():
                    self._allowlist[artifact_class][role][epoch] = set(urls)

    # ============================================================
    # Core Feasibility Query (REQUIRED INTERFACE)
    # ============================================================

    def is_url_allowed(
        self,
        *,
        epoch: int,
        artifact_class: str,
        role: Role,
        url: str,
    ) -> bool:
        """
        Return True iff the exact URL is behaviorally feasible.

        Rules:
        - Missing artifact_class → infeasible
        - Missing role → infeasible
        - Missing epoch bucket → infeasible
        - URL not explicitly listed → infeasible

        This function is:
        - deterministic
        - side-effect free
        - constant-time with respect to snapshot size
        """

        role_map = self._allowlist.get(artifact_class)
        if role_map is None:
            return False

        epoch_map = role_map.get(role)
        if epoch_map is None:
            return False

        allowed_urls = epoch_map.get(epoch)
        if allowed_urls is None:
            return False

        return url in allowed_urls
