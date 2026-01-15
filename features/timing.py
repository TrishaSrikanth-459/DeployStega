"""
Timing feature extractor for behavioral analysis.
"""

from typing import Tuple

from features.extractor import FeatureExtractor
from dataset.benign_dataset import BenignDataset
from dataset.neighboring_dataset import NeighboringDataset
from config import MIN_TIMING_DELTA_SECONDS, MAX_TIMING_DELTA_SECONDS


class TimingFeatureExtractor(FeatureExtractor):
    """
    Extracts intra-user timing distribution for behavioral analysis.
    
    Aggregates timing deltas across all users without preserving per-collaborator
    identity. The adversary cannot determine which users are performing stega
    operations, regardless of per-user commit volume differences.
    """

    @property
    def name(self) -> str:
        return "ft_intra_user_timing"

    def extract(
        self,
        dataset: BenignDataset | NeighboringDataset
    ) -> Tuple[float, ...]:
        """
        Extract inter-action timing distribution from dataset.
        
        Computes Δt = t[i+1] - t[i] for consecutive events per user.
        Returns aggregated distribution across all users.
        
        Args:
            dataset: Dataset containing user activity traces
            
        Returns:
            Tuple of timing deltas (seconds) aggregated across all users
        """
        all_deltas = []

        for user_idx in range(len(dataset)):
            trace = dataset.get_trace(user_idx)

            if len(trace) < 2:
                continue

            for i in range(len(trace) - 1):
                delta_t = trace[i + 1].timestamp - trace[i].timestamp

                if MIN_TIMING_DELTA_SECONDS <= delta_t <= MAX_TIMING_DELTA_SECONDS:
                    all_deltas.append(delta_t)

        return tuple(all_deltas)
