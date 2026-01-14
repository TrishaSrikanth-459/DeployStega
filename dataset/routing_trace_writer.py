"""
dataset/routing_trace_writer.py

Canonical writer + loader for routing interaction traces.

This module is intentionally dumb I/O:
- write JSONL lines in canonical routing-trace schema
- load JSONL lines back into RoutingTraceRecord objects

It does NOT:
- construct InteractionEvents
- build datasets
- infer timing
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable, List, Tuple

from dataset.routing_trace_record import (
    RoutingTraceRecord,
    read_routing_trace_jsonl,
)


# ============================================================
# Writer
# ============================================================

class RoutingTraceWriter:
    """
    Canonical writer for routing interaction traces.

    Emits JSONL records representing routing-layer decisions
    (not InteractionEvents).
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)

    def append(
        self,
        *,
        role: str,
        epoch: int,
        artifact_class: str,
        identifier: Tuple[Any, ...],
        url: str,
        timestamp: float | None = None,
        action_type: str = "route_access",
        metadata: Iterable[Any] = (),
    ) -> None:
        """
        Append a single routing trace record.

        All fields map 1:1 to RoutingTraceRecord.
        """
        record = {
            "role": role,
            "epoch": int(epoch),
            "artifactClass": artifact_class,
            "identifier": list(identifier),
            "url": url,
            "timestamp": float(timestamp if timestamp is not None else time.time()),
            "action_type": action_type,
            "metadata": list(metadata),
        }

        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


# ============================================================
# Loader (canonical inverse)
# ============================================================

def load_routing_trace_jsonl(path: str | Path) -> List[RoutingTraceRecord]:
    """
    Load routing trace JSONL file into RoutingTraceRecord objects.

    This is the canonical inverse of RoutingTraceWriter.append().
    """
    return list(read_routing_trace_jsonl(str(path)))
