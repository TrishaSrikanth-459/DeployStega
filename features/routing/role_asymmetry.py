"""
Routing feature extractor: role asymmetry.

Compares sender vs receiver distributions over artifact_class.
This is routing-specific because it:
- explicitly conditions on role (sender vs receiver)
- detects unbalanced or suspiciously specialized access per role
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from collections import defaultdict

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


def _artifact_class(event: Any) -> Optional[str]:
    c = _get_metadata(event, "artifact_class")
    return str(c) if c is not None else None


class RoleAsymmetryFeatureExtractor(FeatureExtractor):
    """
    Computes total variation distance (TVD) between sender and receiver
    artifact_class distributions.

    Returns:
      ({
        "tvd": float,
        "sender_total": int,
        "receiver_total": int,
        "num_classes": int
      },)
    """

    @property
    def name(self) -> str:
        return "fr_role_asymmetry"

    def extract(
        self,
        dataset: BenignDataset | NeighboringDataset
    ) -> Tuple[Dict[str, float | int],]:
        sender_counts: Dict[str, int] = defaultdict(int)
        receiver_counts: Dict[str, int] = defaultdict(int)

        sender_total = 0
        receiver_total = 0

        for user_idx in range(len(dataset)):
            trace = dataset.get_trace(user_idx)
            for event in trace:
                r = _role(event)
                if r not in ("sender", "receiver"):
                    continue

                c = _artifact_class(event)
                if c is None:
                    continue

                if r == "sender":
                    sender_counts[c] += 1
                    sender_total += 1
                else:
                    receiver_counts[c] += 1
                    receiver_total += 1

        classes = set(sender_counts.keys()) | set(receiver_counts.keys())
        if not classes or sender_total == 0 or receiver_total == 0:
            return ({
                "tvd": 0.0,
                "sender_total": sender_total,
                "receiver_total": receiver_total,
                "num_classes": len(classes),
            },)

        # TVD = 0.5 * sum_c |P_s(c) - P_r(c)|
        tvd = 0.0
        for c in classes:
            ps = sender_counts[c] / sender_total
            pr = receiver_counts[c] / receiver_total
            tvd += abs(ps - pr)
        tvd *= 0.5

        return ({
            "tvd": float(tvd),
            "sender_total": int(sender_total),
            "receiver_total": int(receiver_total),
            "num_classes": int(len(classes)),
        },)
