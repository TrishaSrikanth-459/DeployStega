from typing import Mapping, Tuple, Any, Iterable

class FeatureSet:
    """
    Immutable mapping from feature name to extracted feature values.

    A FeatureSet represents the full observable output of a capability class
    applied to a dataset. It contains no information about how features were
    computed or what they mean.
    """

    __slots__ = ("_features",)

    def __init__(self, features: Mapping[str, Iterable[Any]]):
        self._features: Mapping[str, Tuple[Any, ...]] = {
            name: tuple(values) for name, values in features.items()
        }

        if not self._features:
            raise ValueError("FeatureSet must contain at least one feature")

    def names(self) -> Tuple[str, ...]:
        """
        Returns the feature names in deterministic order.
        """
        return tuple(self._features.keys())

    def get(self, feature_name: str) -> Tuple[Any, ...]:
        return self._features[feature_name]

    def items(self) -> Tuple[Tuple[str, Tuple[Any, ...]], ...]:
        return tuple(
            (name, values) for name, values in self._features.items()
        )

    def __len__(self) -> int:
        return len(self._features)

    def __contains__(self, feature_name: str) -> bool:
        return feature_name in self._features

    def __eq__(self, other:object) -> bool:
        if not isinstance(other, FeatureSet):
            return False
        return self._features == other._features

    def __hash__(self) -> int:
        return hash(tuple(self._features.items()))

    def __repr__(self) -> str:
        return f"FeatureSet(num_features={len(self._features)}"
