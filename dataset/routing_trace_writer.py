from __future__ import annotations

import json
import time
from typing import Any, Iterable, Tuple


class RoutingTraceWriter:
    """
    Canonical writer for routing interaction traces.

    Emits JSONL records representing adversary-observable platform events.
    """

    def __init__(self, path: str):
        self._path = path

    def record(
        self,
        *,
        user_id: str,
        action_type: str,
        artifact_ids: Tuple[Any, ...],
        metadata: Iterable[Any] = (),
        timestamp: float | None = None,
    ) -> None:
        """
        Append a single interaction event to the trace log.
        """
        event = {
            "timestamp": float(timestamp if timestamp is not None else time.time()),
            "user_id": str(user_id),
            "action_type": str(action_type),
            "artifact_ids": list(artifact_ids),
            "metadata": list(metadata),
        }

        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
