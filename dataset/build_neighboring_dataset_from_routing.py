from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple


def _metadata_to_jsonable(metadata: Any) -> Any:
    """
    Ensure metadata is JSON-serializable.

    Expected in codebase: metadata is a tuple of (key, value) pairs.
    We export as a dict; if duplicates exist, last one wins.
    """
    if metadata is None:
        return {}
    try:
        d: Dict[str, Any] = {}
        for k, v in metadata:
            d[str(k)] = v
        return d
    except Exception:
        # Fallback if metadata isn't iterable of pairs
        return {"_raw": repr(metadata)}


def _event_to_record(
    event: Any,
    *,
    user_idx: int,
    event_idx: int,
    label: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convert an InteractionEvent-like object into one JSONL record.
    Uses duck-typing to avoid tight coupling to class internals.
    """
    ts = getattr(event, "timestamp", None)
    action_type = getattr(event, "action_type", None)
    artifact_ids = getattr(event, "artifact_ids", None)
    metadata = getattr(event, "metadata", None)

    rec: Dict[str, Any] = {
        "user_idx": user_idx,
        "event_idx": event_idx,
        "timestamp": ts,
        "action_type": action_type,
        "artifact_ids": list(artifact_ids) if artifact_ids is not None else [],
        "metadata": _metadata_to_jsonable(metadata),
    }
    if label is not None:
        rec["label"] = label
    return rec


def export_dataset_jsonl(
    dataset: Any,
    out_path: str,
    *,
    user_labels: Optional[Dict[int, str]] = None,
) -> None:
    """
    Export any Dataset-like object (BenignDataset or NeighboringDataset)
    to a JSONL file containing per-event records.

    dataset must support:
      - len(dataset)
      - dataset.get_trace(i) returning a Trace-like object
      - trace iterable over events

    user_labels: optional mapping user_idx -> label string
      e.g. {3: "covert"} to mark replaced traces.
    """
    user_labels = user_labels or {}

    with open(out_path, "w", encoding="utf-8") as f:
        for u in range(len(dataset)):
            trace = dataset.get_trace(u)
            label = user_labels.get(u)

            for j, ev in enumerate(trace):
                rec = _event_to_record(ev, user_idx=u, event_idx=j, label=label)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def export_trace_index_json(
    dataset: Any,
    out_path: str,
    *,
    user_labels: Optional[Dict[int, str]] = None,
) -> None:
    """
    Writes a small JSON "index" with dataset-level metadata:
      - number of users
      - per-user number of events
      - optional per-user labels
    """
    user_labels = user_labels or {}

    user_event_counts = []
    for u in range(len(dataset)):
        trace = dataset.get_trace(u)
        user_event_counts.append(len(trace))

    index = {
        "num_users": len(dataset),
        "events_per_user": user_event_counts,
        "user_labels": {str(k): v for k, v in user_labels.items()},
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
