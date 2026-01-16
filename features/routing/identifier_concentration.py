"""
Routing feature extractor: identifier concentration.

Measures how concentrated global access is over artifact IDs.
Dead-drop routing can create suspicious concentration (repeatedly hitting a small set).

Outputs:
- HHI (Herfindahl–Hirschman Index): sum_i p_i^2 (higher => more concentrated)
- normalized_entropy in [0,1]: 1 means uniform, 0 means all mass on one id
"""

from __future__ import annotations

import math
from typing import Any, Dict, Tuple, Optional
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


class IdentifierConcentrationFeatureExtractor(FeatureExtractor):
    """
    Returns:
      ({
        "total_events": int,
        "num_unique_artifacts": int,
        "hhi": float,
        "normalized_entropy": float
      },)
    """

    @property
    def name(self) -> str:
        return "fr_identifier_concentration"

    def extract(
        self,
        dataset: BenignDataset | NeighboringDataset
    ) -> Tuple[Dict[str, float | int],]:
        counts: Dict[Tuple[Any, ...], int] = defaultdict(int)
        total = 0

        for user_idx in range(len(dataset)):
            trace = dataset.get_trace(user_idx)
            for event in trace:
                art = getattr(event, "artifact_ids", ())
                if not art:
                    continue
                aid = tuple(art)
                counts[aid] += 1
                total += 1

        n = len(counts)
        if total == 0 or n == 0:
            return ({
                "total_events": 0,
                "num_unique_artifacts": 0,
                "hhi": 0.0,
                "normalized_entropy": 0.0,
            },)

        # probabilities
        ps = [c / total for c in counts.values()]

        # HHI
        hhi = sum(p * p for p in ps)

        # entropy
        entropy = 0.0
        for p in ps:
            if p > 0:
                entropy -= p * math.log(p)

        # normalize by log(n)
        norm = math.log(n) if n > 1 else 1.0
        normalized_entropy = (entropy / norm) if norm > 0 else 0.0

        return ({
            "total_events": int(total),
            "num_unique_artifacts": int(n),
            "hhi": float(hhi),
            "normalized_entropy": float(normalized_entropy),
        },)
