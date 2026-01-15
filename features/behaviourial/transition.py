"""
Artifact transition feature extractor for behavioral analysis.
"""


from typing import Tuple, Dict, Any
from collections import defaultdict

from features.extractor import FeatureExtractor
from dataset.benign_dataset import BenignDataset
from dataset.neighboring_dataset import NeighboringDataset


def _get_metadata(event, key: str) -> Any:
    for k, v in event.metadata:
        if k == key:
            return v
    return None


class TransitionFeatureExtractor(FeatureExtractor):
    """
    Extracts artifact-class transition distribution.

    Uses event.metadata["artifact_class"], not action_type, since
    routing-derived InteractionEvents typically have constant action_type.
    """

    @property
    def name(self) -> str:
        return "faccess_transition_matrix"

    def extract(
        self,
        dataset: BenignDataset | NeighboringDataset
    ) -> Tuple[Dict[str, Dict[str, float]]]:

        transition_counts = defaultdict(lambda: defaultdict(int))

        for user_idx in range(len(dataset)):
            trace = dataset.get_trace(user_idx)
            if len(trace) < 2:
                continue

            for i in range(len(trace) - 1):
                src = _get_metadata(trace[i], "artifact_class")
                dst = _get_metadata(trace[i + 1], "artifact_class")

                if src is None or dst is None:
                    continue

                transition_counts[str(src)][str(dst)] += 1

        return (self._normalize(transition_counts),)

    @staticmethod
    def _normalize(
        counts: Dict[str, Dict[str, int]]
    ) -> Dict[str, Dict[str, float]]:

        probs: Dict[str, Dict[str, float]] = {}

        for src, targets in counts.items():
            total = sum(targets.values())
            if total == 0:
                continue
            probs[src] = {
                dst: cnt / total for dst, cnt in targets.items()
            }

        return probs
