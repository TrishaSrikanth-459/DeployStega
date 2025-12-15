from dataclasses import dataclass
from typing import Any, Tuple

@dataclass(frozen=True)
class InteractionEvent:
    """
    Atomic, immutable record of a single user action as it would appear in platform logs.

    This is the smallest observable unit in the system. It carries no interpretation, aggregation,
    or security semantics.
    """

    # Absolute timestamp at which the action occurred, in UNIX time
    timestamp: float

    # Categorical label describing the action
    action_type: str

    # Tuple of artifact identifiers accessed or affected by the action.
    # The structure and meaning of identifiers is application-specific
    artifact_ids: Tuple[Any, ...]

    # Optional auxiliary fields (e.g., action specific attributes)
    # Stored as an immutable tuple to preserve hashability
    metadata: Tuple[Any, ...] = ()

