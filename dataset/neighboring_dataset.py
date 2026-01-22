from __future__ import annotations

from typing import Mapping, Dict, Iterator
from types import MappingProxyType

from .interaction_trace import InteractionTrace
from .benign_dataset import BenignDataset


class NeighboringDataset:
    """
    Immutable wrapper representing a k-neighboring dataset D′
    derived from a base benign dataset D by replacing exactly
    k user traces.

    Guarantees:
    - |D′| == |D|
    - Only specified indices differ
    - Ordering is preserved
    - Sequence semantics (__len__, __getitem__, __iter__)
    """

    __slots__ = ("_base_dataset", "_replacements")

    def __init__(
        self,
        base_dataset: BenignDataset,
        replacements: Mapping[int, InteractionTrace],
    ):
        # --------------------
        # Type validation
        # --------------------
        if not isinstance(base_dataset, BenignDataset):
            raise TypeError("base_dataset must be a BenignDataset")
        if not isinstance(replacements, Mapping):
            raise TypeError("replacements must be a mapping {int -> InteractionTrace}")

        dataset_len = len(base_dataset)
        validated: Dict[int, InteractionTrace] = {}

        for idx, trace in replacements.items():
            if not isinstance(idx, int):
                raise TypeError("replacement indices must be integers")
            if idx < 0 or idx >= dataset_len:
                raise IndexError(
                    f"replacement index {idx} out of bounds for dataset of size {dataset_len}"
                )
            if not isinstance(trace, InteractionTrace):
                raise TypeError(
                    "replacement values must be InteractionTrace instances"
                )
            validated[idx] = trace

        if len(validated) != len(replacements):
            raise ValueError("duplicate replacement indices detected")

        # --------------------
        # Freeze internal state
        # --------------------
        self._base_dataset: BenignDataset = base_dataset
        self._replacements: Mapping[int, InteractionTrace] = MappingProxyType(validated)

    # ============================================================
    # Sequence semantics
    # ============================================================

    def __len__(self) -> int:
        """
        Dataset length is unchanged from base dataset.
        """
        return len(self._base_dataset)

    def __getitem__(self, index: int) -> InteractionTrace:
        """
        Sequence access.

        Replacement is visible iff index ∈ replacements.
        """
        if not isinstance(index, int):
            raise TypeError("index must be an integer")
        if index < 0 or index >= len(self):
            raise IndexError("index out of bounds")

        if index in self._replacements:
            return self._replacements[index]
        return self._base_dataset[index]

    def __iter__(self) -> Iterator[InteractionTrace]:
        """
        Deterministic iteration over dataset traces.
        """
        for i in range(len(self)):
            yield self[i]

    # ============================================================
    # Explicit accessor (optional, semantic clarity)
    # ============================================================

    def get_trace(self, index: int) -> InteractionTrace:
        """
        Explicit accessor equivalent to __getitem__.
        """
        return self[index]
