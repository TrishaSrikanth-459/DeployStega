"""
Determinism tests for DeadDropResolver.

These tests verify:
1. Identical inputs always produce identical outputs
2. Different epochs influence the routing decision

These tests intentionally:
- Use an allow-all feasibility region
- Avoid assumptions about URL structure
- Exercise the full resolver pipeline
"""

from routing.dead_drop_function.dead_drop_resolver import DeadDropResolver
from routing.dead_drop_function.feasibility_region import FeasibilityRegion
from routing.dead_drop_function.repository_snapshot.serializer import read_snapshot


# ============================================================
# Feasibility stub (must implement is_url_allowed)
# ============================================================

class AllowAllFeasibility(FeasibilityRegion):
    """
    Feasibility region that allows all URLs.
    Used to isolate deterministic behavior.
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
    """
    Construct a DeadDropResolver from a snapshot on disk.
    """

    snapshot = read_snapshot(snapshot_path)

    # Infer owner/repo from the first artifact identifier
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

def test_resolve_is_deterministic():
    """
    Same inputs MUST produce identical outputs.
    """

    resolver = make_resolver("tests/snapshots/minimal.json")

    params = dict(
        epoch=42,
        sender_id="alice",
        receiver_id="bob",
        role="sender",
    )

    r1 = resolver.resolve(**params)
    r2 = resolver.resolve(**params)

    assert r1 == r2, "Resolver is not deterministic"


def test_epoch_affects_resolution():
    """
    Different epochs SHOULD influence routing decisions.
    """

    resolver = make_resolver("tests/snapshots/minimal.json")

    r1 = resolver.resolve(
        epoch=1,
        sender_id="alice",
        receiver_id="bob",
        role="sender",
    )

    r2 = resolver.resolve(
        epoch=2,
        sender_id="alice",
        receiver_id="bob",
        role="sender",
    )

    assert r1 != r2, "Epoch does not influence routing decision"
