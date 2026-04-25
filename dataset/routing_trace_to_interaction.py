from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple, DefaultDict
from collections import defaultdict

from dataset.interaction_event import InteractionEvent
from dataset.interaction_trace import InteractionTrace
from dataset.routing_trace_record import RoutingTraceRecord


@dataclass(frozen=True)
class TimingPolicy:
    epoch_origin_unix: int
    epoch_duration_seconds: int
    spread_within_epoch_seconds: float = 0.0


def _stable_artifact_ids(rec: RoutingTraceRecord) -> Tuple[Any, ...]:
    return (rec.artifact_class, *rec.identifier)


def _stable_metadata(rec: RoutingTraceRecord) -> Tuple[Any, ...]:
    base = (
        ("role", rec.role),
        ("epoch", rec.epoch),
        ("url", rec.url),
        ("action_type", rec.action_type),
        ("artifact_class", rec.artifact_class),
    )

    semantic_part: Tuple[Tuple[Any, Any], ...] = ()
    if rec.semantic_ref is not None:
        semantic_part += (("semantic_ref", rec.semantic_ref),)
    if rec.semantic_text is not None:
        semantic_part += (("semantic_text", rec.semantic_text),)
    if rec.semantic_meaning is not None:
        semantic_part += (("semantic_meaning", rec.semantic_meaning),)
    if rec.semantic_label is not None:
        semantic_part += (("semantic_label", rec.semantic_label),)
    if rec.semantic_content_type is not None:
        semantic_part += (("semantic_content_type", rec.semantic_content_type),)

    return base + tuple(rec.metadata) + semantic_part


def _synthesize_timestamp(
    policy: TimingPolicy,
    rec: RoutingTraceRecord,
    index_within_bucket: int,
    bucket_size: int,
) -> float:
    base = float(policy.epoch_origin_unix + rec.epoch * policy.epoch_duration_seconds)
    if policy.spread_within_epoch_seconds <= 0.0 or bucket_size <= 1:
        return base
    frac = index_within_bucket / max(1, bucket_size - 1)
    return base + frac * float(policy.spread_within_epoch_seconds)


def routing_record_to_event(
    rec: RoutingTraceRecord,
    *,
    timing_policy: Optional[TimingPolicy] = None,
    index_within_bucket: int = 0,
    bucket_size: int = 1,
) -> InteractionEvent:
    if rec.timestamp is not None:
        ts = float(rec.timestamp)
    else:
        if timing_policy is None:
            raise ValueError("RoutingTraceRecord has no timestamp; timing_policy required")
        ts = _synthesize_timestamp(
            timing_policy, rec, index_within_bucket=index_within_bucket, bucket_size=bucket_size
        )

    return InteractionEvent(
        timestamp=ts,
        action_type=rec.action_type,
        artifact_ids=_stable_artifact_ids(rec),
        metadata=_stable_metadata(rec),
        semantic_ref=rec.semantic_ref,
        semantic_content=rec.semantic_text,
        semantic_label=rec.semantic_label,
        semantic_type=rec.semantic_content_type,
    )


def records_to_events_by_user(
    *,
    records: Iterable[RoutingTraceRecord],
    user_key: str = "role",
    timing_policy: Optional[TimingPolicy] = None,
) -> Dict[str, Tuple[InteractionEvent, ...]]:
    buckets: DefaultDict[str, List[RoutingTraceRecord]] = defaultdict(list)

    for rec in records:
        if user_key == "role":
            key = rec.role
        elif user_key == "role_epoch":
            key = f"{rec.role}:{rec.epoch}"
        elif user_key == "none":
            key = "all"
        else:
            raise ValueError(f"Unsupported user_key: {user_key}")
        buckets[key].append(rec)

    if not buckets:
        raise ValueError("No routing trace records provided")

    out: Dict[str, Tuple[InteractionEvent, ...]] = {}

    for user, recs in buckets.items():
        def sort_key(r: RoutingTraceRecord) -> Tuple[Any, ...]:
            t = r.timestamp if r.timestamp is not None else float("inf")
            return (t, r.epoch, r.stable_key())

        recs_sorted = sorted(recs, key=sort_key)

        if any(r.timestamp is None for r in recs_sorted) and timing_policy is None:
            raise ValueError("Routing trace contains records without timestamps; timing_policy required")

        by_epoch: DefaultDict[int, List[int]] = defaultdict(list)
        for idx, r in enumerate(recs_sorted):
            by_epoch[r.epoch].append(idx)

        events: List[InteractionEvent] = []
        for idx, r in enumerate(recs_sorted):
            if r.timestamp is not None:
                ts = float(r.timestamp)
                # For records with timestamp, we still need to pass something to routing_record_to_event.
                # The function will ignore these because rec.timestamp is set.
                pos = 0
                bucket_size = 1
            else:
                indices = by_epoch[r.epoch]
                pos = indices.index(idx)
                bucket_size = len(indices)
                ts = _synthesize_timestamp(
                    timing_policy, r, index_within_bucket=pos, bucket_size=bucket_size
                )

            events.append(routing_record_to_event(
                r,
                timing_policy=timing_policy,
                index_within_bucket=pos,
                bucket_size=bucket_size
            ))

        events_sorted = sorted(events, key=lambda e: (e.timestamp, e.action_type, e.artifact_ids, e.metadata))
        out[user] = tuple(events_sorted)

    return out


def events_to_traces(events_by_user: Dict[str, Tuple[InteractionEvent, ...]]) -> Dict[str, InteractionTrace]:
    return {user: InteractionTrace(events) for user, events in events_by_user.items()}


def build_interaction_traces(
    *,
    records: Iterable[RoutingTraceRecord],
    user_key: str = "role",
    timing_policy: Optional[TimingPolicy] = None,
) -> Dict[str, InteractionTrace]:
    events_by_user = records_to_events_by_user(records=records, user_key=user_key, timing_policy=timing_policy)
    return events_to_traces(events_by_user)
