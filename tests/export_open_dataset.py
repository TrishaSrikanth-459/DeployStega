"""
scripts/export_open_dataset.py

Export an open, reusable interaction dataset from a routing trace.

This script:
- Loads canonical RoutingTraceRecord objects
- Converts them into InteractionTraces
- Optionally labels users (e.g., covert vs benign)
- Writes a clean JSONL dataset suitable for release

This file is intentionally thin orchestration code.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict

from dataset.routing_trace_writer import load_routing_trace_jsonl
from dataset.routing_trace_to_interaction import (
    build_interaction_traces,
    TimingPolicy,
)
from dataset.interaction_trace import InteractionTrace


# ============================================================
# Argument parsing
# ============================================================

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export an open interaction dataset from a routing trace"
    )

    parser.add_argument(
        "--routing-trace",
        required=True,
        help="Path to routing_trace.jsonl",
    )

    parser.add_argument(
        "--out-dir",
        required=True,
        help="Output directory for exported dataset",
    )

    parser.add_argument(
        "--timing-policy",
        default="use_record_timestamp",
        choices=[
            "use_record_timestamp",
            "synthesize_from_epoch",
        ],
        help="How to assign timestamps to interaction events",
    )

    parser.add_argument(
        "--epoch-origin-unix",
        type=float,
        default=None,
        help="Epoch origin UNIX timestamp (required for synthesize_from_epoch)",
    )

    parser.add_argument(
        "--epoch-duration-seconds",
        type=float,
        default=None,
        help="Seconds per epoch (required for synthesize_from_epoch)",
    )

    parser.add_argument(
        "--label-users",
        default="",
        help='Comma-separated labels like "0:covert,1:benign"',
    )

    return parser.parse_args()


# ============================================================
# Label parsing
# ============================================================

def _parse_user_labels(spec: str) -> Dict[int, str]:
    labels: Dict[int, str] = {}

    if not spec:
        return labels

    for part in spec.split(","):
        user_idx, label = part.split(":")
        labels[int(user_idx)] = label

    return labels


# ============================================================
# Serialization helpers
# ============================================================

def _serialize_trace(
    trace: InteractionTrace,
    label: str | None,
) -> Dict:
    return {
        "label": label,
        "events": [
            {
                "timestamp": e.timestamp,
                "action_type": e.action_type,
                "artifact_ids": list(e.artifact_ids),
                "metadata": list(e.metadata),
            }
            for e in trace
        ],
    }


# ============================================================
# Main
# ============================================================

def main() -> None:
    args = _parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------
    # Load routing trace (canonical)
    # ------------------------------
    records = load_routing_trace_jsonl(args.routing_trace)

    # ------------------------------
    # Construct TimingPolicy
    # ------------------------------
    if args.timing_policy == "use_record_timestamp":
        # Routing trace already contains timestamps
        timing_policy = None

    elif args.timing_policy == "synthesize_from_epoch":
        if args.epoch_origin_unix is None or args.epoch_duration_seconds is None:
            raise ValueError(
                "synthesize_from_epoch requires "
                "--epoch-origin-unix and --epoch-duration-seconds"
            )

        timing_policy = TimingPolicy(
            epoch_origin_unix=int(args.epoch_origin_unix),
            epoch_duration_seconds=int(args.epoch_duration_seconds),
        )

    else:
        raise AssertionError("unreachable")

    # ------------------------------
    # Build interaction traces
    # ------------------------------
    traces_by_user = build_interaction_traces(
        records=records,
        timing_policy=timing_policy,
    )

    # ------------------------------
    # Apply labels
    # ------------------------------
    user_labels = _parse_user_labels(args.label_users)

    # ------------------------------
    # Export dataset
    # ------------------------------
    out_path = out_dir / "interaction_dataset.jsonl"

    with out_path.open("w", encoding="utf-8") as f:
        for user_idx, trace in enumerate(traces_by_user.values()):
            label = user_labels.get(user_idx)
            record = _serialize_trace(trace, label)
            f.write(json.dumps(record) + "\n")

    print(f"[OK] Exported {len(traces_by_user)} user traces to {out_path}")


if __name__ == "__main__":
    main()
