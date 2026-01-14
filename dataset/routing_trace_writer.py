from __future__ import annotations

import json
import time
from typing import Any, Iterable, Tuple, List
from pathlib import Path

from dataset.routing_trace_record import RoutingTraceRecord

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

    def load_routing_trace_jsonl(path: str | Path) -> List[RoutingTraceRecord]:
        """
        Load a routing trace JSONL file into RoutingTraceRecord objects.

        This is the canonical inverse of RoutingTraceWriter.record().
        """
        path = Path(path)
        records: List[RoutingTraceRecord] = []

        with path.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Invalid JSON on line {line_num} of {path}"
                    ) from e

                records.append(
                    RoutingTraceRecord(
                        timestamp=obj["timestamp"],
                        user_id=obj["user_id"],
                        action_type=obj["action_type"],
                        artifact_ids=tuple(obj["artifact_ids"]),
                        metadata=tuple(obj.get("metadata", ())),
                    )
                )

        if not records:
            raise ValueError(f"No routing trace records found in {path}")

        return records
