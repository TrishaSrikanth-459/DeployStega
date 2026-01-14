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


@dataclass(frozen=True)
class TimingPolicy:
    """
    If routing trace lines do NOT include timestamps, we deterministically synthesize them.

    timestamp = epoch_origin_unix + epoch * epoch_duration_seconds + per_record_offset

    per_record_offset is deterministic based on record index within a (role, epoch) bucket.

    NOTE: this is *not* a behavioral model; it's a deterministic scaffolding to make a valid trace.
    Replace later with your behavioral generator timing.
    """
    epoch_origin_unix: int
    epoch_duration_seconds: int
    # maximum number of seconds we may spread events inside an epoch bucket deterministically
    spread_within_epoch_seconds: float = 0.0


def _stable_artifact_ids(rec: RoutingTraceRecord) -> Tuple[Any, ...]:
    return (rec.artifact_class, *rec.identifier)


def _stable_metadata(rec: RoutingTraceRecord) -> Tuple[Any, ...]:
    # Store log-relevant fields that features might want (URL, epoch, role, etc.)
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
    base = float(policy.epoch_origin_unix + rec.epoch * policy.epoch_duration_seconds)

    if policy.spread_within_epoch_seconds <= 0.0 or bucket_size <= 1:
        return base

    # Deterministic spread in [0, spread] using stable position
    # (not random; purely based on ordering)
    frac = index_within_bucket / max(1, bucket_size - 1)
    return base + frac * float(policy.spread_within_epoch_seconds)


def records_to_events_by_user(
    *,
    records: Iterable[RoutingTraceRecord],
    user_key: str = "role",
    timing_policy: Optional[TimingPolicy] = None,
) -> Dict[str, Tuple[InteractionEvent, ...]]:
    """
    Convert routing trace records into per-user event tuples.

    user_key controls grouping:
      - "role" (default): produces two users: "sender" and "receiver"
      - "role_epoch": splits users by (role, epoch) -- rarely desired
      - You can extend this later to real user IDs.

    If record.timestamp is None:
      - timing_policy MUST be provided to synthesize timestamps deterministically.
    """
    # 1) group records into user buckets
    buckets: DefaultDict[str, List[RoutingTraceRecord]] = defaultdict(list)

    for rec in records:
        if user_key == "role":
            key = rec.role
        elif user_key == "role_epoch":
            key = f"{rec.role}:{rec.epoch}"
        else:
            raise ValueError(f"Unsupported user_key: {user_key}")
        buckets[key].append(rec)

    # 2) for each bucket, enforce deterministic ordering
    out: Dict[str, Tuple[InteractionEvent, ...]] = {}

    for user, recs in buckets.items():
        # deterministic sort:
        # - if timestamp exists, use it; else use epoch then stable_key
        def sort_key(r: RoutingTraceRecord) -> Tuple:
            t = r.timestamp if r.timestamp is not None else float("inf")
            return (t, r.epoch, r.stable_key())

        recs_sorted = sorted(recs, key=sort_key)

        # 3) assign timestamps if missing, but do it per (role, epoch) bucket deterministically
        if any(r.timestamp is None for r in recs_sorted):
            if timing_policy is None:
                raise ValueError(
                    "Routing trace contains records with no timestamp; provide timing_policy to synthesize timestamps."
                )

        # Precompute within-epoch ordering for synthesis
        by_epoch: DefaultDict[int, List[int]] = defaultdict(list)
        for idx, r in enumerate(recs_sorted):
            by_epoch[r.epoch].append(idx)

        events: List[InteractionEvent] = []
        for idx, r in enumerate(recs_sorted):
            ts: float
            if r.timestamp is not None:
                ts = float(r.timestamp)
            else:
                epoch_indices = by_epoch[r.epoch]
                bucket_pos = epoch_indices.index(idx)
                ts = _synthesize_timestamp(timing_policy, r, bucket_pos, len(epoch_indices))

            events.append(
                InteractionEvent(
                    timestamp=ts,
                    action_type=r.action_type,
                    artifact_ids=_stable_artifact_ids(r),
                    metadata=_stable_metadata(r),
                )
            )

        # final sort by timestamp then deterministic tie-break on content
        events_sorted = sorted(
            events,
            key=lambda e: (e.timestamp, e.action_type, e.artifact_ids, e.metadata),
        )

        out[user] = tuple(events_sorted)

    if not out:
        raise ValueError("No user buckets created from records")

    return out


def events_to_traces(events_by_user: Dict[str, Tuple[InteractionEvent, ...]]) -> Dict[str, InteractionTrace]:
    """
    Wrap per-user immutable event tuples into InteractionTrace objects.
    """
    traces: Dict[str, InteractionTrace] = {}
    for user, events in events_by_user.items():
        traces[user] = InteractionTrace(events)
    return traces
