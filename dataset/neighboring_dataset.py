from typing import Mapping, Dict
from types import MappingProxyType

from .interaction_trace import InteractionTrace
from .benign_dataset import BenignDataset

class NeighboringDataset:
    """
    Immutable wrapper representing a k-neighboring dataset D
    derived from a base benign dataset D by replacing exactly
    k user traces
    """

    __slots__ = ("_base_dataset", "_replacements")

    def __init__(self, base_dataset: BenignDataset, replacements: Mapping[int, InteractionTrace]):
        # Type Checks
        if not isinstance(base_dataset, BenignDataset):
            raise TypeError("base_dataset must be a BenignDataset")
        if not isinstance(replacements, Mapping):
            raise TypeError("replacements must be a mapping {int -> InteractionTrace}")

        # Enforce index validity and replacement type
        validated: Dict[int, InteractionTrace] = {}
        dataset_len = len(base_dataset)

        for idx, trace in replacements.items():
            if not isinstance(idx, int):
                raise TypeError("replacement indices must be integers")
            if idx < 0 or idx >= dataset_len:
                raise IndexError(f"replacement index {idx} out of bounds for dataset of size {dataset_len}")
            if not isinstance(trace, InteractionTrace):
                raise TypeError("replacement values must be InteractionTrace instances")
            validated[idx] = trace

        # Enforce exactly k replacements
        if len(validated) != len(replacements):
            raise ValueError("duplicate replacement indices detected")

        # Freeze internal state
        self._base_dataset: BenignDataset = base_dataset
        self._replacements: Mapping[int, InteractionTrace] = MappingProxyType(validated)

    # Public API
    def __len__(self) -> int:
        """
        Dataset length is unchanged from base dataset.
        """
        return len(self._base_dataset)

    def get_trace(self, index: int) -> InteractionTrace:
        """
        Return the InteractionTrace at index.
        Replacement is visible iff index ∈ replacements.
        """
        if not isinstance(index, int):
            raise TypeError("index must be an integer")
        if index < 0 or index >= len(self):
            raise IndexError("index out of bounds")
        if index in self._replacements:
            return self._replacements[index]
        return self._base_dataset.get_trace(index)
