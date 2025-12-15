from typing import Iterable, Tuple
from .interaction_trace import InteractionTrace

class BenignDataset:
    """
    Immutable dataset consisting of one interaction trace per user
    """

    __slots__ = ("_traces",)

    def __init__(self, traces: Iterable[InteractionTrace]):
        self._traces: Tuple[InteractionTrace, ...] = tuple(traces)

        if not self._traces:
            raise ValueError("BenignDataset must contain at least one trace")

        def __len__(self) -> int:
            return len(self._traces)

        def get_trace(self, user_index: int) -> InteractionTrace:
            return self._traces[user_index]

        def __getitem__(self, user_index: int) -> InteractionTrace:
            return self.get_trace(user_index)

        def traces(self) -> Tuple[InteractionTrace, ...]:
            """
            Returns the underlying immutable tuple of interaction traces
            """
            return self._traces

        def __repr__(self) -> str:
            return f"BenignDataset(num_users={len(self._traces)}"
