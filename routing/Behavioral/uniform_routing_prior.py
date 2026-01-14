from typing import Dict, Iterable

from .routing_prior import RoutingPrior
from routing.dead_drop_function.repository_snapshot.schema import ArtifactClass


class UniformRoutingPrior(RoutingPrior):
    """
    Uniform routing prior over all feasible routing artifact classes.

    Intended as a baseline prior; prevalence-weighted priors may
    replace this implementation.
    """

    def artifact_class_weights(
        self,
        *,
        epoch: int,
        role: str,
        feasible_classes: Iterable[ArtifactClass],
    ) -> Dict[ArtifactClass, float]:
        return {cls: 1.0 for cls in feasible_classes}
