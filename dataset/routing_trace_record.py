from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
import json


@dataclass(frozen=True)
class RoutingTraceRecord:
    role: str
    epoch: int
    artifact_class: str
    identifier: Tuple[Any, ...]
    url: str

    experiment_id: Optional[str] = None
    timestamp: Optional[float] = None
    action_type: str = "route_access"
    metadata: Tuple[Any, ...] = ()

    # Embedded semantic payload (optional)
    semantic_text: Optional[str] = None
    semantic_meaning: Optional[str] = None
    semantic_ref: Optional[str] = None
    semantic_label: Optional[str] = None
    semantic_content_type: Optional[str] = None

    def stable_key(self) -> Tuple[Any, ...]:
        return (
            self.experiment_id,
            self.role,
            self.epoch,
            self.artifact_class,
            self.identifier,
            self.url,
            self.timestamp if self.timestamp is not None else -1.0,
            self.action_type,
            self.metadata,
            self.semantic_ref,
        )


def _require(obj: Dict[str, Any], key: str) -> Any:
    if key not in obj:
        raise ValueError(f"RoutingTraceRecord missing required field: {key}")
    return obj[key]


def _coerce_identifier(value: Any) -> Tuple[Any, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    raise TypeError(f"identifier must be list or tuple, got {type(value).__name__}")


def parse_routing_trace_line(obj: Dict[str, Any]) -> RoutingTraceRecord:
    role = str(_require(obj, "role")).strip().lower()
    if role not in ("sender", "receiver"):
        raise ValueError(f"Invalid role in routing trace: {role}")

    epoch = _require(obj, "epoch")
    if not isinstance(epoch, int) or epoch < 0:
        raise ValueError(f"Invalid epoch in routing trace: {epoch}")

    artifact_class = obj.get("artifact_class", obj.get("artifactClass"))
    if artifact_class is None:
        raise ValueError("Missing required field: artifact_class")
    artifact_class = str(artifact_class).strip()
    if not artifact_class:
        raise ValueError("artifact_class must be non-empty")

    identifier = _coerce_identifier(_require(obj, "identifier"))

    url = str(_require(obj, "url")).strip()
    if not url:
        raise ValueError("url must be non-empty")

    experiment_id = obj.get("experiment_id")
    if experiment_id is not None:
        experiment_id = str(experiment_id)

    timestamp = obj.get("timestamp")
    if timestamp is not None:
        if not isinstance(timestamp, (int, float)):
            raise TypeError("timestamp must be numeric")
        timestamp = float(timestamp)

    action_type = obj.get("action_type", obj.get("actionType", "route_access"))
    action_type = str(action_type).strip() if action_type else "route_access"

    metadata_raw = obj.get("metadata", ())
    if metadata_raw is None:
        metadata = ()
    elif isinstance(metadata_raw, tuple):
        metadata = metadata_raw
    elif isinstance(metadata_raw, list):
        metadata = tuple(metadata_raw)
    else:
        metadata = (metadata_raw,)

    return RoutingTraceRecord(
        role=role,
        epoch=epoch,
        artifact_class=artifact_class,
        identifier=identifier,
        url=url,
        experiment_id=experiment_id,
        timestamp=timestamp,
        action_type=action_type,
        metadata=metadata,
        semantic_text=obj.get("semantic_text"),
        semantic_meaning=obj.get("semantic_meaning"),
        semantic_ref=obj.get("semantic_ref"),
        semantic_label=obj.get("semantic_label"),
        semantic_content_type=obj.get("semantic_content_type"),
    )


def read_routing_trace_jsonl(path: str) -> Tuple[RoutingTraceRecord, ...]:
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
                raise TypeError(f"JSONL line {lineno} must be a JSON object")
            records.append(parse_routing_trace_line(obj))

    if not records:
        raise ValueError(f"No routing trace records found in {path}")

    return tuple(records)
