"""
Role symmetry tests for DeadDropResolver.

Invariant enforced:

For fixed (epoch, sender_id, receiver_id):
- sender and receiver MUST resolve to the same artifact class
- sender and receiver MUST resolve to the same identifier
- URLs MAY differ (role-specific access patterns are allowed)
"""

from routing.dead_drop_function.dead_drop_resolver import DeadDropResolver
from routing.dead_drop_function.feasibility_region import FeasibilityRegion
from routing.dead_drop_function.repository_snapshot.serializer import read_snapshot


# ============================================================
# Feasibility stub (allow everything)
# ============================================================

class AllowAllFeasibility(FeasibilityRegion):
    """
    Feasibility region that allows all URLs.
    Used to isolate role symmetry behavior.
    """

    def is_url_allowed(
        self,
        *,
        epoch: int,
        artifact_class: str,
        role: str,
        url: str,
    ) -> bool:
        return True


# ============================================================
# Resolver construction helper
# ============================================================

def make_resolver(snapshot_path: str) -> DeadDropResolver:
    snapshot = read_snapshot(snapshot_path)

    first_class = next(iter(snapshot.artifacts))
    first_artifact = snapshot.artifacts[first_class][0]
    owner, repo = first_artifact.identifier[:2]

    return DeadDropResolver(
        snapshot=snapshot,
        feasibility_region=AllowAllFeasibility(),
        owner=owner,
        repo=repo,
    )


# ============================================================
# Tests
# ============================================================

def test_sender_receiver_role_symmetry():
    """
    Sender and receiver must rendezvous on the same artifact.
    """

    resolver = make_resolver("tests/snapshots/minimal.json")

    params = dict(
        epoch=1337,
        sender_id="alice",
        receiver_id="bob",
    )

    sender_result = resolver.resolve(
        **params,
        role="sender",
    )

    receiver_result = resolver.resolve(
        **params,
        role="receiver",
    )

    # --------------------------------------------------------
    # Hard invariants
    # --------------------------------------------------------

    assert (
        sender_result["artifactClass"]
        == receiver_result["artifactClass"]
    ), "Artifact class differs between sender and receiver"

    assert (
        sender_result["identifier"]
        == receiver_result["identifier"]
    ), "Identifier differs between sender and receiver"

    # --------------------------------------------------------
    # Soft invariant (URLs may differ)
    # --------------------------------------------------------

    assert isinstance(sender_result["url"], str)
    assert isinstance(receiver_result["url"], str)
