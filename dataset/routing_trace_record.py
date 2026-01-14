"""
dataset/routing_trace_record.py

Defines a canonical, minimal routing-trace record and a JSONL loader.

This module is intentionally "dumb I/O":
- parse JSONL lines
- validate required fields
- normalize identifier types
- return immutable records

It does NOT:
- construct InteractionEvents
- build datasets
- infer timing unless explicitly configured
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, Optional, Tuple
import json


@dataclass(frozen=True)
class RoutingTraceRecord:
    """
    One routing decision / action emission as logged by your routing layer.

    Required:
      - role: "sender" | "receiver"
      - epoch: int
      - artifact_class: str
      - identifier: tuple[Any, ...]
      - url: str

    Optional:
      - timestamp: float (unix seconds)
      - action_type: str (defaults to "route_access")
      - metadata: tuple[Any, ...] (freeform, immutable)
    """
    role: str
    epoch: int
    artifact_class: str
    identifier: Tuple[Any, ...]
    url: str
    timestamp: Optional[float] = None
    action_type: str = "route_access"
    metadata: Tuple[Any, ...] = ()

    def stable_key(self) -> Tuple:
        """
        Deterministic tie-break key (for sorting / ordering when needed).
        """
        return (
            self.role,
            self.epoch,
            self.artifact_class,
            self.identifier,
            self.url,
            self.timestamp if self.timestamp is not None else -1.0,
            self.action_type,
            self.metadata,
        )


def _require(d: Dict[str, Any], k: str) -> Any:
    if k not in d:
        raise ValueError(f"RoutingTraceRecord missing required field: {k}")
    return d[k]


def _coerce_identifier(x: Any) -> Tuple[Any, ...]:
    # Accept tuple or list in JSON
    if isinstance(x, tuple):
        return x
    if isinstance(x, list):
        return tuple(x)
    raise TypeError(f"identifier must be list/tuple; got {type(x).__name__}")


def parse_routing_trace_line(obj: Dict[str, Any]) -> RoutingTraceRecord:
    role = str(_require(obj, "role")).strip().lower()
    if role not in ("sender", "receiver"):
        raise ValueError(f"Invalid role in routing trace: {role}")

    epoch = _require(obj, "epoch")
    if not isinstance(epoch, int) or epoch < 0:
        raise ValueError(f"Invalid epoch in routing trace: {epoch}")

    artifact_class = str(_require(obj, "artifactClass")).strip()
    if not artifact_class:
        raise ValueError("artifactClass must be non-empty")

    identifier_raw = _require(obj, "identifier")
    identifier = _coerce_identifier(identifier_raw)

    url = str(_require(obj, "url")).strip()
    if not url:
        raise ValueError("url must be non-empty")

    timestamp = obj.get("timestamp")
    if timestamp is not None:
        if not isinstance(timestamp, (int, float)):
            raise TypeError("timestamp must be int|float unix seconds if provided")
        timestamp = float(timestamp)

    action_type = obj.get("action_type", "route_access")
    action_type = str(action_type).strip() if action_type is not None else "route_access"
    if not action_type:
        action_type = "route_access"

    metadata_raw = obj.get("metadata", ())
    if metadata_raw is None:
        metadata = ()
    elif isinstance(metadata_raw, tuple):
        metadata = metadata_raw
    elif isinstance(metadata_raw, list):
        metadata = tuple(metadata_raw)
    else:
        # allow scalar metadata by boxing it
        metadata = (metadata_raw,)

    return RoutingTraceRecord(
        role=role,
        epoch=epoch,
        artifact_class=artifact_class,
        identifier=identifier,
        url=url,
        timestamp=timestamp,
        action_type=action_type,
        metadata=metadata,
    )


def read_routing_trace_jsonl(path: str) -> Tuple[RoutingTraceRecord, ...]:
    """
    Load JSONL routing trace file into an immutable tuple of RoutingTraceRecord.

    Expected JSON fields per line:
      - role
      - epoch
      - artifactClass
      - identifier
      - url
    Optional:
      - timestamp
      - action_type
      - metadata
    """
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception as e:
                raise ValueError(f"Invalid JSON on line {lineno} in {path}") from e
            if not isinstance(obj, dict):
                raise TypeError(f"JSONL line {lineno} must be object/dict")
            records.append(parse_routing_trace_line(obj))

    if not records:
        raise ValueError(f"No records found in routing trace: {path}")

    return tuple(records)
