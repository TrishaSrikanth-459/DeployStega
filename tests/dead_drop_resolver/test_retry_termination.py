"""
Retry termination tests for DeadDropResolver.

Invariant enforced:

If at least one feasible route exists, the resolver must terminate
in finite time, even if early candidates are rejected.
"""

from routing.dead_drop_function.dead_drop_resolver import DeadDropResolver
from routing.dead_drop_function.feasibility_region import FeasibilityRegion
from routing.dead_drop_function.repository_snapshot.serializer import read_snapshot


# ============================================================
# Feasibility region that rejects first K attempts
# ============================================================

class RejectFirstKFeasibility(FeasibilityRegion):
    """
    Reject the first K feasibility checks, then allow everything.
    Used to test resolver retry termination.
    """

    def __init__(self, k: int):
        self.k = k
        self.calls = 0

    def is_url_allowed(
        self,
        *,
        epoch: int,
        artifact_class: str,
        role: str,
        url: str,
    ) -> bool:
        self.calls += 1
        return self.calls > self.k


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

def test_resolver_terminates_after_retries():
    """
    Resolver must eventually terminate if a feasible route exists,
    even after many rejected attempts.
    """

    # Reject a large but finite number of attempts
    feasibility = RejectFirstKFeasibility(k=50)

    resolver = make_resolver(
        "tests/snapshots/minimal.json",
        feasibility,
    )

    result = resolver.resolve(
        epoch=999,
        sender_id="alice",
        receiver_id="bob",
        role="sender",
    )

    # --------------------------------------------------------
    # Termination + sanity checks
    # --------------------------------------------------------

    assert isinstance(result, dict)
    assert "artifactClass" in result
    assert "identifier" in result
    assert "url" in result

    # Ensure retries actually occurred
    assert feasibility.calls > 50, (
        "Feasibility region did not observe enough retries"
    )
