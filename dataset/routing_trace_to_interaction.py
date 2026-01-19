"""
dataset/routing_trace_to_interaction.py

Converts RoutingTraceRecord -> InteractionEvent -> InteractionTrace.

Key design decision:
- An InteractionEvent must represent what the adversary sees in logs.
- We encode artifact identity as a tuple that is stable and extractor-friendly.

artifact_ids format (recommended, stable):
  (artifact_class, *identifier)

We also include the concrete URL and routing fields in metadata (immutable).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple, DefaultDict
from collections import defaultdict

from dataset.interaction_event import InteractionEvent
from dataset.interaction_trace import InteractionTrace
from dataset.routing_trace_record import RoutingTraceRecord


# ============================================================
# Timing policy (deterministic scaffolding only)
# ============================================================

@dataclass(frozen=True)
class TimingPolicy:
    """
    If routing trace lines do NOT include timestamps, we deterministically synthesize them.

    timestamp =
        epoch_origin_unix
        + epoch * epoch_duration_seconds
        + per_record_offset

    NOTE:
    - This is NOT a behavioral model.
    - This is deterministic scaffolding so traces are well-formed.
    """
    epoch_origin_unix: int
    epoch_duration_seconds: int
    spread_within_epoch_seconds: float = 0.0


# ============================================================
# Internal helpers
# ============================================================

def _stable_artifact_ids(rec: RoutingTraceRecord) -> Tuple[Any, ...]:
    return (rec.artifact_class, *rec.identifier)


def _stable_metadata(rec: RoutingTraceRecord) -> Tuple[Any, ...]:
    return (
        ("role", rec.role),
        ("epoch", rec.epoch),
        ("url", rec.url),
        ("action_type", rec.action_type),
        ("artifact_class", rec.artifact_class),
    ) + tuple(rec.metadata)


def _synthesize_timestamp(
    policy: TimingPolicy,
    rec: RoutingTraceRecord,
    index_within_bucket: int,
    bucket_size: int,
) -> float:
    base = float(
        policy.epoch_origin_unix
        + rec.epoch * policy.epoch_duration_seconds
    )

    if policy.spread_within_epoch_seconds <= 0.0 or bucket_size <= 1:
        return base

    frac = index_within_bucket / max(1, bucket_size - 1)
    return base + frac * float(policy.spread_within_epoch_seconds)


# ============================================================
# Record → Event (atomic adapter)
# ============================================================

def routing_record_to_event(
    rec: RoutingTraceRecord,
    *,
    timing_policy: Optional[TimingPolicy] = None,
    index_within_bucket: int = 0,
    bucket_size: int = 1,
) -> InteractionEvent:
    """
    Convert a single RoutingTraceRecord into an InteractionEvent.

    Used for:
    - unit tests
    - documentation
    - sanity checking

    If rec.timestamp is None, timing_policy MUST be provided.
    """

    if rec.timestamp is not None:
        ts = float(rec.timestamp)
    else:
        if timing_policy is None:
            raise ValueError(
                "RoutingTraceRecord has no timestamp; timing_policy required"
            )
        ts = _synthesize_timestamp(
            timing_policy,
            rec,
            index_within_bucket=index_within_bucket,
            bucket_size=bucket_size,
        )

    return InteractionEvent(
        timestamp=ts,
        action_type=rec.action_type,
        artifact_ids=_stable_artifact_ids(rec),
        metadata=_stable_metadata(rec),
        semantic_ref=rec.semantic.semantic_ref if rec.semantic else None,
        semantic_content=rec.semantic.content if rec.semantic else None,
        semantic_label=rec.semantic.label if rec.semantic else None,
        semantic_type=rec.semantic.content_type if rec.semantic else None,
    )


# ============================================================
# Records → Events (per user)
# ============================================================

def records_to_events_by_user(
    *,
    records: Iterable[RoutingTraceRecord],
    user_key: str = "role",
    timing_policy: Optional[TimingPolicy] = None,
) -> Dict[str, Tuple[InteractionEvent, ...]]:
    """
    Convert routing trace records into per-user InteractionEvent tuples.

    user_key:
      - "role"       → users are "sender", "receiver"
      - "role_epoch" → users are "sender:epoch", etc.
    """

    buckets: DefaultDict[str, List[RoutingTraceRecord]] = defaultdict(list)

    for rec in records:
        if user_key == "role":
            key = rec.role
        elif user_key == "role_epoch":
            key = f"{rec.role}:{rec.epoch}"
        else:
            raise ValueError(f"Unsupported user_key: {user_key}")

        buckets[key].append(rec)

    if not buckets:
        raise ValueError("No routing trace records provided")

    out: Dict[str, Tuple[InteractionEvent, ...]] = {}

    for user, recs in buckets.items():
        # Deterministic ordering
        def sort_key(r: RoutingTraceRecord) -> Tuple[Any, ...]:
            t = r.timestamp if r.timestamp is not None else float("inf")
            return (t, r.epoch, r.stable_key())

        recs_sorted = sorted(recs, key=sort_key)

        if any(r.timestamp is None for r in recs_sorted) and timing_policy is None:
            raise ValueError(
                "Routing trace contains records without timestamps; timing_policy required"
            )

        by_epoch: DefaultDict[int, List[int]] = defaultdict(list)
        for idx, r in enumerate(recs_sorted):
            by_epoch[r.epoch].append(idx)

        events: List[InteractionEvent] = []
        for idx, r in enumerate(recs_sorted):
            if r.timestamp is not None:
                ts = float(r.timestamp)
            else:
                indices = by_epoch[r.epoch]
                pos = indices.index(idx)
                ts = _synthesize_timestamp(
                    timing_policy,
                    r,
                    index_within_bucket=pos,
                    bucket_size=len(indices),
                )

            events.append(
                InteractionEvent(
                    timestamp=ts,
                    action_type=r.action_type,
                    artifact_ids=_stable_artifact_ids(r),
                    metadata=_stable_metadata(r),
                )
            )

        events_sorted = sorted(
            events,
            key=lambda e: (e.timestamp, e.action_type, e.artifact_ids, e.metadata),
        )

        out[user] = tuple(events_sorted)

    return out


# ============================================================
# Events → Traces
# ============================================================

def events_to_traces(
    events_by_user: Dict[str, Tuple[InteractionEvent, ...]]
) -> Dict[str, InteractionTrace]:
    traces: Dict[str, InteractionTrace] = {}
    for user, events in events_by_user.items():
        traces[user] = InteractionTrace(events)
    return traces


# ============================================================
# Public entry points
# ============================================================

def build_interaction_traces(
    *,
    records: Iterable[RoutingTraceRecord],
    user_key: str = "role",
    timing_policy: Optional[TimingPolicy] = None,
) -> Dict[str, InteractionTrace]:
    """
    Canonical conversion entry point:
        RoutingTraceRecord* → InteractionTrace per user
    """
    events_by_user = records_to_events_by_user(
        records=records,
        user_key=user_key,
        timing_policy=timing_policy,
    )
    return events_to_traces(events_by_user)


def build_interaction_trace(
    *,
    records: Iterable[RoutingTraceRecord],
    user_key: str = "role",
    timing_policy: Optional[TimingPolicy] = None,
) -> InteractionTrace:
    """
    Convenience wrapper for cases where exactly ONE InteractionTrace is expected.
    """
    traces = build_interaction_traces(
        records=records,
        user_key=user_key,
        timing_policy=timing_policy,
    )

    if len(traces) != 1:
        raise ValueError(
            f"Expected exactly one InteractionTrace, got {len(traces)}"
        )

    return next(iter(traces.values()))
