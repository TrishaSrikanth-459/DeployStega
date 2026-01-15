"""
Artifact transition feature extractor for behavioral analysis.
"""

from typing import Tuple, Dict
from collections import defaultdict

from features.extractor import FeatureExtractor
from dataset.benign_dataset import BenignDataset
from dataset.neighboring_dataset import NeighboringDataset
from config import GITHUB_EVENT_TO_ARTIFACT_CLASS


class TransitionFeatureExtractor(FeatureExtractor):
    """
    Extracts artifact class transition distribution for behavioral analysis.
    
    Captures sequential access patterns between artifact classes (e.g.,
    Issue → PullRequest, Commit → IssueComment).
    
    Aggregates transitions across all users without preserving per-collaborator
    identity. The adversary cannot determine which users are performing stega
    operations, regardless of per-user transition pattern differences.
    """

    @property
    def name(self) -> str:
        return "faccess_transition_matrix"

    def extract(
        self,
        dataset: BenignDataset | NeighboringDataset
    ) -> Tuple[Dict[str, Dict[str, float]]]:
        """
        Extract transition matrix from dataset.
        
        Maps event types to artifact classes, counts transitions between
        consecutive classes, and normalizes to probabilities.
        
        Args:
            dataset: Dataset containing user activity traces
            
        Returns:
            Tuple containing transition matrix: {source: {target: P(target|source)}}
        """
        transition_counts = defaultdict(lambda: defaultdict(int))

        for user_idx in range(len(dataset)):
            trace = dataset.get_trace(user_idx)

            if len(trace) < 2:
                continue

            for i in range(len(trace) - 1):
                source_event = trace[i]
                target_event = trace[i + 1]

                source_class = GITHUB_EVENT_TO_ARTIFACT_CLASS.get(
                    source_event.action_type,
                    source_event.action_type
                )
                target_class = GITHUB_EVENT_TO_ARTIFACT_CLASS.get(
                    target_event.action_type,
                    target_event.action_type
                )

                transition_counts[source_class][target_class] += 1

        transition_matrix = self._normalize_transitions(transition_counts)

        return (transition_matrix,)

    def _normalize_transitions(
        self,
        counts: Dict[str, Dict[str, int]]
    ) -> Dict[str, Dict[str, float]]:
        """
        Convert transition counts to probabilities.
        
        Returns:
            Nested dict: {source: {target: P(target|source)}}
        """
        transition_probs = {}

        for source_class, target_counts in counts.items():
            total_transitions = sum(target_counts.values())

            transition_probs[source_class] = {
                target_class: count / total_transitions
                for target_class, count in target_counts.items()
            }

        return transition_probs
