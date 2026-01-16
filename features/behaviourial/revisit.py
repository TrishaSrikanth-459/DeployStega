"""
Artifact revisit behavior feature extractor for behavioral analysis.
"""

from typing import Tuple

from features.extractor import FeatureExtractor
from dataset.benign_dataset import BenignDataset
from dataset.neighboring_dataset import NeighboringDataset


class RevisitFeatureExtractor(FeatureExtractor):
    """
    Extracts artifact revisit behavior distribution for behavioral analysis.
    
    Computes revisit patterns: how often users return to previously accessed
    artifacts, number of unique artifacts accessed, and maximum revisit counts.
    
    Aggregates metrics across all users without preserving per-collaborator
    identity. The adversary cannot determine which users are performing stega
    operations, regardless of per-user revisit pattern differences.
    """

    @property
    def name(self) -> str:
        return "f_artifact_revisit"

    def extract(
        self,
        dataset: BenignDataset | NeighboringDataset
    ) -> Tuple[Tuple[float, ...], Tuple[int, ...], Tuple[int, ...]]:
        """
        Extract artifact revisit behavior metrics from dataset.
        
        Tracks artifact accesses, counts revisits, and computes per-user metrics
        aggregated across all users.
        
        Args:
            dataset: Dataset containing user activity traces
            
        Returns:
            Three tuples:
            - Revisit rates (proportion of revisits per user)
            - Unique artifact counts (distinct artifacts per user)
            - Max revisit counts (maximum revisits to single artifact per user)
        """
        revisit_rates = []
        unique_artifacts_counts = []
        max_revisits_counts = []

        for user_idx in range(len(dataset)):
            trace = dataset.get_trace(user_idx)

            if len(trace) < 2:
                continue

            seen_artifacts = set()
            artifact_visit_counts = {}
            revisit_count = 0

            for event in trace:
                artifact_id = event.artifact_ids[0] if event.artifact_ids else None

                if artifact_id is None:
                    continue

                if artifact_id in seen_artifacts:
                    revisit_count += 1
                else:
                    seen_artifacts.add(artifact_id)

                artifact_visit_counts[artifact_id] = (
                    artifact_visit_counts.get(artifact_id, 0) + 1
                )

            if len(seen_artifacts) == 0:
                continue

            total_actions = len(trace)
            revisit_rate = revisit_count / total_actions
            unique_artifacts = len(seen_artifacts)
            max_revisits = max(artifact_visit_counts.values()) - 1

            revisit_rates.append(revisit_rate)
            unique_artifacts_counts.append(unique_artifacts)
            max_revisits_counts.append(max_revisits)

        return (
            tuple(revisit_rates),
            tuple(unique_artifacts_counts),
            tuple(max_revisits_counts)
        )
