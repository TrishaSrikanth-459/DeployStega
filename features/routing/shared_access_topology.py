"""
Routing feature extractor: shared access topology.

This is NOT the same as single-user transition topology.
Instead, it measures overlap structure across roles at the artifact-id level:

- fraction of artifacts touched by both roles
- fraction touched only by sender
- fraction touched only by receiver

These are multi-user routing observables induced by dead-drop behavior.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, Set

from features.extractor import FeatureExtractor
from dataset.benign_dataset import BenignDataset
from dataset.neighboring_dataset import NeighboringDataset


def _get_metadata(event: Any, key: str) -> Optional[Any]:
    md = getattr(event, "metadata", None)
    if not md:
        return None
    for k, v in md:
        if k == key:
            return v
    return None


def _role(event: Any) -> Optional[str]:
    r = _get_metadata(event, "role")
    return str(r) if r is not None else None


class SharedAccessTopologyFeatureExtractor(FeatureExtractor):
    """
    Returns:
      ({
        "shared_fraction": float,
        "sender_only_fraction": float,
        "receiver_only_fraction": float,
        "total_unique_artifacts": int
      },)
    """

    @property
    def name(self) -> str:
        return "fr_shared_access_topology"

    def extract(
        self,
        dataset: BenignDataset | NeighboringDataset
    ) -> Tuple[Dict[str, float | int],]:
        sender: Set[Tuple[Any, ...]] = set()
        receiver: Set[Tuple[Any, ...]] = set()

        for user_idx in range(len(dataset)):
            trace = dataset.get_trace(user_idx)
            for event in trace:
                r = _role(event)
                if r not in ("sender", "receiver"):
                    continue

                art = getattr(event, "artifact_ids", ())
                if not art:
                    continue

                aid = tuple(art)
                if r == "sender":
                    sender.add(aid)
                else:
                    receiver.add(aid)

        union = sender | receiver
        if not union:
            return ({
                "shared_fraction": 0.0,
                "sender_only_fraction": 0.0,
                "receiver_only_fraction": 0.0,
                "total_unique_artifacts": 0,
            },)

        shared = sender & receiver
        sender_only = sender - receiver
        receiver_only = receiver - sender

        total = len(union)
        return ({
            "shared_fraction": len(shared) / total,
            "sender_only_fraction": len(sender_only) / total,
            "receiver_only_fraction": len(receiver_only) / total,
            "total_unique_artifacts": total,
        },)
