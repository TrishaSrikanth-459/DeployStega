"""
dataset/routing_trace_record.py

Defines the canonical routing-trace record used as the single source of truth
for DeployStega experiments and dataset export.

This module is intentionally minimal and log-faithful.

A routing trace represents adversary-visible platform logs. It may optionally
carry references to semantic artifacts (or inline semantic payloads) when
explicitly enabled by the experiment.

This module:
- Parses JSONL routing traces
- Validates required fields
- Normalizes identifiers
- Preserves real timestamps
- Cleanly supports semantic payload linkage

It does NOT:
- Construct InteractionEvents
- Infer timing
- Perform feature extraction
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
import json


# ============================================================
# Semantic payload (optional, explicit)
# ============================================================

@dataclass(frozen=True)
class SemanticPayload:
    """
    Explicit semantic content associated with a routing event.

    This payload is optional and only present when the sender modifies
    or accesses semantic artifacts (e.g., issue body, PR comment, commit message).

    Fields:
      - semantic_ref: stable identifier used to link events and artifacts
      - content: raw semantic text (stego or benign)
      - label: "covert" | "benign"
      - content_type: descriptive string (e.g., issue_body, pr_comment)
    """

    semantic_ref: str
    content: str
    label: str
    content_type: str


# ============================================================
# Core routing record
# ============================================================

@dataclass(frozen=True)
class RoutingTraceRecord:
    """
    One routing-layer interaction as emitted by the DeployStega resolver.

    Required:
      - role: "sender" | "receiver"
      - epoch: int
      - artifact_class: str
      - identifier: tuple[Any, ...]
      - url: str

    Optional:
      - experiment_id: str
      - timestamp: float (unix seconds)
      - action_type: str
      - metadata: tuple[(key, value), ...]
      - semantic: SemanticPayload (explicit semantic content, if any)
    """

    role: str
    epoch: int
    artifact_class: str
    identifier: Tuple[Any, ...]
    url: str

    experiment_id: Optional[str] = None
    timestamp: Optional[float] = None
    action_type: str = "route_access"
    metadata: Tuple[Tuple[Any, Any], ...] = ()
    semantic: Optional[SemanticPayload] = None

    def stable_key(self) -> Tuple[Any, ...]:
        """
        Deterministic ordering key for reproducibility.
        """
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
            self.semantic.semantic_ref if self.semantic else None,
        )


# ============================================================
# Parsing helpers
# ============================================================

def _require(obj: Dict[str, Any], key: str) -> Any:
    if key not in obj:
        raise ValueError(f"RoutingTraceRecord missing required field: {key}")
    return obj[key]


def _coerce_identifier(value: Any) -> Tuple[Any, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    raise TypeError(
        f"identifier must be list or tuple, got {type(value).__name__}"
    )


def _parse_semantic(obj: Dict[str, Any]) -> Optional[SemanticPayload]:
    """
    Parse optional semantic payload if present.
    """
    semantic_obj = obj.get("semantic")
    if semantic_obj is None:
        return None

    if not isinstance(semantic_obj, dict):
        raise TypeError("semantic field must be an object")

    return SemanticPayload(
        semantic_ref=str(_require(semantic_obj, "semantic_ref")),
        content=str(_require(semantic_obj, "content")),
        label=str(_require(semantic_obj, "label")),
        content_type=str(_require(semantic_obj, "content_type")),
    )


# ============================================================
# Record parser
# ============================================================

def parse_routing_trace_line(obj: Dict[str, Any]) -> RoutingTraceRecord:
    """
    Parse and validate a single JSON object into a RoutingTraceRecord.
    """

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

    action_type = obj.get("action_type", "route_access")
    action_type = str(action_type).strip() if action_type else "route_access"

    metadata_raw = obj.get("metadata", ())
    if metadata_raw is None:
        metadata: Tuple[Tuple[Any, Any], ...] = ()
    elif isinstance(metadata_raw, list):
        metadata = tuple(tuple(pair) for pair in metadata_raw)
    elif isinstance(metadata_raw, tuple):
        metadata = metadata_raw
    else:
        raise TypeError("metadata must be list or tuple of pairs")

    semantic = _parse_semantic(obj)

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
        semantic=semantic,
    )


# ============================================================
# JSONL loader
# ============================================================

def read_routing_trace_jsonl(path: str) -> Tuple[RoutingTraceRecord, ...]:
    """
    Load a JSONL routing trace file into an immutable tuple of RoutingTraceRecord.
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
                raise ValueError(
                    f"Invalid JSON on line {lineno} in {path}"
                ) from e

            if not isinstance(obj, dict):
                raise TypeError(
                    f"JSONL line {lineno} must be a JSON object"
                )

            records.append(parse_routing_trace_line(obj))

    if not records:
        raise ValueError(f"No routing trace records found in {path}")

    return tuple(records)
