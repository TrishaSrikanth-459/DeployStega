"""
Event type frequency feature extractor for behavioral analysis.
"""

from typing import Tuple, Dict
from collections import defaultdict

from features.extractor import FeatureExtractor
from dataset.benign_dataset import BenignDataset
from dataset.neighboring_dataset import NeighboringDataset


def _get_metadata(event, key: str):
    for k, v in event.metadata:
        if k == key:
            return v
    return None


class FrequencyFeatureExtractor(FeatureExtractor):
    """
    Extracts artifact class frequency distribution for behavioral analysis.
    
    Aggregates frequencies across all users without preserving per-collaborator
    identity. The adversary cannot determine which users are performing stega
    operations, regardless of per-user artifact class preferences.
    """

    @property
    def name(self) -> str:
        return "f_event_type_frequency"

    def extract(
        self,
        dataset: BenignDataset | NeighboringDataset
    ) -> Tuple[Dict[str, float]]:
        """
        Extract event type frequency distribution from dataset.
        
        Args:
            dataset: Dataset containing user activity traces
            
        Returns:
            Tuple containing frequency distribution: {artifact_class: P(class)}
        """
        class_counts = defaultdict(int)
        total_events = 0

        for user_idx in range(len(dataset)):
            trace = dataset.get_trace(user_idx)

            for event in trace:
                artifact_class = _get_metadata(event, "artifact_class")
                
                if artifact_class is None:
                    continue

                class_counts[str(artifact_class)] += 1
                total_events += 1

        if total_events == 0:
            frequency_dist = {}
        else:
            frequency_dist = {
                artifact_class: count / total_events
                for artifact_class, count in class_counts.items()
            }

        return (frequency_dist,) 
