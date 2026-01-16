"""
Event type frequency feature extractor for behavioral analysis.
"""

from typing import Tuple, Dict
from collections import defaultdict

from features.extractor import FeatureExtractor
from dataset.benign_dataset import BenignDataset
from dataset.neighboring_dataset import NeighboringDataset
from config import GITHUB_EVENT_TO_ARTIFACT_CLASS


class FrequencyFeatureExtractor(FeatureExtractor):
    """
    Extracts artifact class frequency distribution for behavioral analysis.
    
    Counts how often each artifact class appears and normalizes to probabilities,
    showing P(class) = proportion of actions interacting with that class.
    
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
        
        Maps event types to artifact classes, counts occurrences, and
        normalizes to probabilities.
        
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
                artifact_class = GITHUB_EVENT_TO_ARTIFACT_CLASS.get(
                    event.action_type,
                    event.action_type
                )

                class_counts[artifact_class] += 1
                total_events += 1

        if total_events == 0:
            frequency_dist = {}
        else:
            frequency_dist = {
                artifact_class: count / total_events
                for artifact_class, count in class_counts.items()
            }

        return (frequency_dist,)
