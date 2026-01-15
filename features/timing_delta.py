from typing import Tuple

from features.extractor import FeatureExtractor
from dataset.benign_dataset import BenignDataset
from dataset.neighboring_dataset import NeighboringDataset
from config import MIN_TIMING_DELTA_SECONDS, MAX_TIMING_DELTA_SECONDS


class TimingFeatureExtractor(FeatureExtractor):
    """
    Extracts inter-event timing deltas across all users.
    """

    @property
    def name(self) -> str:
        return "ft_intra_user_timing"

    def extract(
        self,
        dataset: BenignDataset | NeighboringDataset
    ) -> Tuple[float, ...]:
        deltas = []

        for user_idx in range(len(dataset)):
            trace = dataset.get_trace(user_idx)

            for i in range(len(trace) - 1):
                delta = trace[i + 1].timestamp - trace[i].timestamp
                if MIN_TIMING_DELTA_SECONDS <= delta <= MAX_TIMING_DELTA_SECONDS:
                    deltas.append(delta)

        return tuple(deltas)
