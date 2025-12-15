from typing import Iterable, Dict

from features.extractor import FeatureExtractor
from features.feature_set import FeatureSet
from dataset.benign_dataset import BenignDataset
from dataset.neighboring_dataset import NeighboringDataset

class FeatureExtractionPipeline:
    """
    Mechanically applies a fixed set of feature extractors to a dataset
    and returns the resulting FeatureSet

    The pipline is intentionally agnostic to:
    - whether the dataset is D or D'
    - which users are replaced
    - what features mean
    """

    __slots__ = ("_extractors",)

    def __init__(self, extractors: Iterable[FeatureExtractor]):
        self._extractors = tuple(extractors)

        if not self._extractors:
            raise ValueError("FeatureExtractionPipline requires at least one extractor")

        # Enforce unique feature names
        names = [ext.name for ext in self._extractors]
        if len(names) != len(set(names)):
            raise ValueError("FeatureExtractionPipline names must be unique")

    def run(self, dataset: BenignDataset | NeighboringDataset,) -> FeatureSet:
        """
        Applies all feature extractors to the dataset and returns a FeatureSet
        """

        extracted: Dict[str, tuple] = {}
        for extractor in self._extractors:
            values = extractor.extract(dataset)
            extracted[extractor.name] = tuple(values)

        return FeatureSet(extracted)
