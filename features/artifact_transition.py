from typing import Tuple, Dict
from collections import defaultdict

from features.extractor import FeatureExtractor
from dataset.benign_dataset import BenignDataset
from dataset.neighboring_dataset import NeighboringDataset


class TransitionFeatureExtractor(FeatureExtractor):
    """
    Extracts artifact-class transition probabilities.
    """

    @property
    def name(self) -> str:
        return "faccess_transition_matrix"

    def extract(
        self,
        dataset: BenignDataset | NeighboringDataset
    ) -> Tuple[Dict[str, Dict[str, float]]]:
        counts = defaultdict(lambda: defaultdict(int))

        for user_idx in range(len(dataset)):
            trace = dataset.get_trace(user_idx)

            for i in range(len(trace) - 1):
                src = trace[i].action_type
                dst = trace[i + 1].action_type
                counts[src][dst] += 1

        return (self._normalize(counts),)

    def _normalize(
        self,
        counts: Dict[str, Dict[str, int]]
    ) -> Dict[str, Dict[str, float]]:
        probs = {}

        for src, targets in counts.items():
            total = sum(targets.values())
            probs[src] = {
                dst: cnt / total for dst, cnt in targets.items()
            }

        return probs
