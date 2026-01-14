from __future__ import annotations

import json
from collections import defaultdict
from typing import Iterable, Dict, List

from dataset.interaction_event import InteractionEvent
from dataset.interaction_trace import InteractionTrace
from dataset.benign_dataset import BenignDataset


class TraceBuilder:
    """
    Deterministically constructs InteractionTrace and BenignDataset objects
    from raw routing trace logs.

    This module performs NO inference, learning, or filtering.
    It is a pure structural transformation.
    """

    @staticmethod
    def from_jsonl(path: str) -> BenignDataset:
        """
        Build a BenignDataset from a routing_trace.jsonl file.

        Expected JSONL schema per line:
        {
            "timestamp": float,
            "user_id": str,
            "action_type": str,
            "artifact_ids": [...],
            "metadata": [...]   # optional
        }
        """
        per_user_events: Dict[str, List[InteractionEvent]] = defaultdict(list)

        with open(path, "r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Invalid JSON at line {line_number}: {e}"
                    ) from e

                try:
                    event = InteractionEvent(
                        timestamp=float(raw["timestamp"]),
                        action_type=str(raw["action_type"]),
                        artifact_ids=tuple(raw["artifact_ids"]),
                        metadata=tuple(raw.get("metadata", ())),
                    )
                    user_id = str(raw["user_id"])
                except KeyError as e:
                    raise ValueError(
                        f"Missing required field {e} at line {line_number}"
                    ) from e

                per_user_events[user_id].append(event)

        if not per_user_events:
            raise ValueError("No events found in routing trace")

        # Deterministic ordering
        traces: List[InteractionTrace] = []

        for user_id in sorted(per_user_events.keys()):
            events = sorted(
                per_user_events[user_id],
                key=lambda e: e.timestamp,
            )
            traces.append(InteractionTrace(events))

        return BenignDataset(traces)
