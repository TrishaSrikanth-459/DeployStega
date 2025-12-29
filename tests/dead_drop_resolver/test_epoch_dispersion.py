"""
Epoch dispersion tests for DeadDropResolver.

Invariant enforced:

Across a sequence of epochs, the resolver should not collapse
onto a single artifact. We expect dispersion, not randomness.
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
    Used to isolate epoch dispersion behavior.
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

def test_epoch_dispersion_over_time():
    """
    Resolver should exhibit dispersion across epochs.

    This test does NOT require:
    - every epoch to differ
    - uniform distribution

    It only requires that routing does not collapse
    to a single artifact forever.
    """

    resolver = make_resolver("tests/snapshots/minimal.json")

    sender_id = "alice"
    receiver_id = "bob"
    role = "sender"

    results = set()

    for epoch in range(0, 25):
        r = resolver.resolve(
            epoch=epoch,
            sender_id=sender_id,
            receiver_id=receiver_id,
            role=role,
        )

        # Track (artifactClass, identifier) only
        results.add(
            (r["artifactClass"], r["identifier"])
        )

    # We require dispersion, not randomness
    assert len(results) > 1, (
        "Resolver shows no dispersion across epochs; "
        "all epochs map to the same artifact"
    )
