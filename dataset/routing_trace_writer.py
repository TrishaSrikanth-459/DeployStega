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
from typing import Any, Iterable, List, Tuple, Optional

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

    Semantic content support:
    - Semantic content is OPTIONAL.
    - When present, it is embedded directly at the top level
      of the routing trace record.
    - No external semantic files are assumed.
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        *,
        role: str,
        epoch: int,
        artifact_class: str,
        identifier: Tuple[Any, ...],
        url: str,
        timestamp: Optional[float] = None,
        action_type: str = "route_access",
        metadata: Iterable[Any] = (),

        # --------------------------------------------------
        # Optional: embedded semantic content
        # --------------------------------------------------
        semantic_text: Optional[str] = None,
        semantic_meaning: Optional[str] = None,
        semantic_label: Optional[str] = None,          # "benign" | "covert"
        semantic_content_type: Optional[str] = None,   # e.g. "issue_comment"
    ) -> None:
        """
        Append a single routing trace record.

        Schema guarantees:
        - artifact_class is written in snake_case (canonical)
        - identifier is always serialized as a list
        - timestamp is always present (real UNIX seconds)
        - semantic fields, if provided, are written as flat top-level keys

        This function performs NO validation beyond basic normalization.
        Validation happens at load time.
        """

        record: dict[str, Any] = {
            "role": role,
            "epoch": int(epoch),
            "artifact_class": artifact_class,
            "identifier": list(identifier),
            "url": url,
            "timestamp": float(timestamp if timestamp is not None else time.time()),
            "action_type": action_type,
            "metadata": list(metadata),
        }

        # --------------------------------------------------
        # Embed semantic content only if explicitly provided
        # --------------------------------------------------
        if semantic_text is not None:
            record["semantic_text"] = str(semantic_text)

        if semantic_meaning is not None:
            record["semantic_meaning"] = str(semantic_meaning)

        if semantic_label is not None:
            record["semantic_label"] = str(semantic_label)

        if semantic_content_type is not None:
            record["semantic_content_type"] = str(semantic_content_type)

        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ============================================================
# Loader (canonical inverse)
# ============================================================

def load_routing_trace_jsonl(path: str | Path) -> List[RoutingTraceRecord]:
    """
    Load routing trace JSONL file into RoutingTraceRecord objects.

    This is the canonical inverse of RoutingTraceWriter.append().
    """
    return list(read_routing_trace_jsonl(str(path)))
