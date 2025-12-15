from typing import Iterable, Tuple, Iterator
from .interaction_event import InteractionEvent

class InteractionTrace:
    """
    immutable, ordered sequence of InteractionEvent Objects representing a single user's full
    interaction history
    """

    __slots__ = ("_events",)

    def __init__(self, events: Iterable[InteractionEvent]):
        self._events: Tuple[InteractionEvent, ...] = tuple(events)

    def __len__(self) -> int:
        return len(self._events)

    def __getitem__(self, idx: int) -> InteractionEvent:
        return self._events[idx]

    def __iter__(self) -> Iterator[InteractionEvent]:
        return iter(self._events)

    def events(self) -> Tuple[InteractionEvent, ...]:
        """
        returns the underlying immutable tuple of InteractionEvent objects
        """
        return self._events

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InteractionTrace):
            return False
        return self._events == other._events

    def __hash__(self) -> int:
        return hash(self._events)

    def __repr__(self) -> str:
        return f"InteractionTrace(num_events={len(self._events)})"

