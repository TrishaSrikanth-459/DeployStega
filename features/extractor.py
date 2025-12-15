from abc import ABC, abstractmethod
from typing import Tuple, Any

from dataset.benign_dataset import BenignDataset
from dataset.neighboring_dataset import NeighboringDataset

class FeatureExtractor(ABC):
    """
    Abstract base class for all feature extractors in the capability class

    A FeatureExtractor defines a deterministic mapping from a dataset
    (benign or neighboring) to a finite set of feature values
    """

    @property
    @abstractmethod

    def name(self) -> str:
        """
        Unique, stable name identifying this feature
        """
        raise NotImplementedError()

    @abstractmethod
    def extract(self, dataset: BenignDataset | NeighboringDataset,) -> Tuple[Any, ...]:
        """
        Extracts a finite set of feature values from the dataset.

        The extractor:
            - Must be deterministic
            - Must not mutate the dataset
            - Must not depend on whether the dataset is D or D'
            - Must return only derived feature values
        """
        raise NotImplementedError()

    
