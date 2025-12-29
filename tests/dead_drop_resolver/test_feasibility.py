"""
Feasibility tests for DeadDropResolver.

These tests verify that:
1. The resolver respects feasibility constraints
2. The resolver retries when encountering infeasible routes
"""

from routing.dead_drop_function.dead_drop_resolver import DeadDropResolver
from routing.dead_drop_function.feasibility_region import FeasibilityRegion
from routing.dead_drop_function.repository_snapshot.serializer import read_snapshot


# ============================================================
# Feasibility regions for testing
# ============================================================

class RejectAllIssuesFeasibility(FeasibilityRegion):
    """
    Reject all URLs associated with Issues.
    Accept everything else.
    """

    def is_url_allowed(
        self,
        *,
        epoch: int,
        artifact_class: str,
        role: str,
        url: str,
    ) -> bool:
        return artifact_class != "Issues"


class RejectFirstURLFeasibility(FeasibilityRegion):
    """
    Reject the first URL seen per resolve() call.
    Accept all subsequent URLs.
    """

    def __init__(self):
        self._seen = False

    def is_url_allowed(
        self,
        *,
        epoch: int,
        artifact_class: str,
        role: str,
        url: str,
    ) -> bool:
        if not self._seen:
            self._seen = True
            return False
        return True


# ============================================================
# Resolver construction helper
# ============================================================

def make_resolver(snapshot_path: str, feasibility: FeasibilityRegion) -> DeadDropResolver:
    snapshot = read_snapshot(snapshot_path)

    first_class = next(iter(snapshot.artifacts))
    first_artifact = snapshot.artifacts[first_class][0]
    owner, repo = first_artifact.identifier[:2]

    return DeadDropResolver(
        snapshot=snapshot,
        feasibility_region=feasibility,
        owner=owner,
        repo=repo,
    )


# ============================================================
# Tests
# ============================================================

def test_feasibility_filters_artifact_classes():
    """
    Resolver must skip infeasible artifact classes.
    """

    resolver = make_resolver(
        "tests/snapshots/minimal.json",
        RejectAllIssuesFeasibility(),
    )

    result = resolver.resolve(
        epoch=10,
        sender_id="alice",
        receiver_id="bob",
        role="sender",
    )

    assert result["artifactClass"] != "Issues", (
        "Resolver returned an infeasible artifact class"
    )


def test_resolver_retries_on_infeasible_url():
    """
    Resolver must retry when the first URL is infeasible.
    """

    resolver = make_resolver(
        "tests/snapshots/minimal.json",
        RejectFirstURLFeasibility(),
    )

    result = resolver.resolve(
        epoch=20,
        sender_id="alice",
        receiver_id="bob",
        role="sender",
    )

    assert isinstance(result["url"], str)
