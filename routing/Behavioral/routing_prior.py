from abc import ABC, abstractmethod
from typing import Dict, Iterable

from routing.dead_drop_function.repository_snapshot.schema import ArtifactClass


class RoutingPrior(ABC):
    """
    Abstract routing prior over routing-namespace artifact classes.

    The prior biases artifact-class selection while respecting:
      - snapshot feasibility
      - behavioral feasibility
      - identifier stability
    """

    @abstractmethod
    def artifact_class_weights(
        self,
        *,
        epoch: int,
        role: str,
        feasible_classes: Iterable[ArtifactClass],
    ) -> Dict[ArtifactClass, float]:
        raise NotImplementedError
