"""
Routing feature extractor: shared access overlap.

Measures how much the sender and receiver overlap on *artifact identity*
(i.e., they touched the same artifact_ids at least once).

This is routing-specific because it is:
- multi-user (requires at least two roles)
- identifier-level (uses artifact_ids)
"""

from __future__ import annotations

from typing import Any, Dict, Tuple, Optional, Set

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


class SharedAccessFeatureExtractor(FeatureExtractor):
    """
    Outputs overlap metrics between sender and receiver artifact sets.

    Returns a single dict in a 1-tuple:
      {
        "sender_unique": int,
        "receiver_unique": int,
        "shared": int,
        "union": int,
        "jaccard": float
      }
    """

    @property
    def name(self) -> str:
        return "fr_shared_access_overlap"

    def extract(
        self,
        dataset: BenignDataset | NeighboringDataset
    ) -> Tuple[Dict[str, float | int],]:
        sender: Set[Tuple[Any, ...]] = set()
        receiver: Set[Tuple[Any, ...]] = set()

        for user_idx in range(len(dataset)):
            trace = dataset.get_trace(user_idx)
            for event in trace:
                rid = _role(event)
                if rid not in ("sender", "receiver"):
                    continue

                art = getattr(event, "artifact_ids", ())
                if not art:
                    continue

                art_tup = tuple(art)
                if rid == "sender":
                    sender.add(art_tup)
                else:
                    receiver.add(art_tup)

        shared = sender.intersection(receiver)
        union = sender.union(receiver)

        sender_unique = len(sender - receiver)
        receiver_unique = len(receiver - sender)

        out: Dict[str, float | int] = {
            "sender_unique": sender_unique,
            "receiver_unique": receiver_unique,
            "shared": len(shared),
            "union": len(union),
            "jaccard": (len(shared) / len(union)) if union else 0.0,
        }
        return (out,)
