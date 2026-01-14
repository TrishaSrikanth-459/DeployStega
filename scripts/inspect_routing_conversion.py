from __future__ import annotations

import argparse
from pprint import pprint

from dataset.routing_trace_record import read_routing_trace_jsonl
from dataset.routing_trace_to_interaction import (
    build_interaction_traces,
    TimingPolicy,
)
from dataset.benign_dataset import BenignDataset


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Inspect conversion from routing trace → interaction events → traces → dataset"
    )
    ap.add_argument(
        "--routing-trace",
        required=True,
        help="Path to routing_trace.jsonl",
    )
    ap.add_argument(
        "--epoch-origin-unix",
        type=int,
        required=True,
        help="Epoch origin UNIX time (required if routing trace has no timestamps)",
    )
    ap.add_argument(
        "--epoch-duration-seconds",
        type=int,
        required=True,
        help="Epoch duration in seconds",
    )
    ap.add_argument(
        "--spread-within-epoch-seconds",
        type=float,
        default=0.0,
        help="Optional deterministic spread inside each epoch bucket",
    )
    ap.add_argument(
        "--user-key",
        default="role",
        choices=["role", "role_epoch"],
    )
    args = ap.parse_args()

    # --------------------------------------------------
    # Step 1: load routing trace records
    # --------------------------------------------------
    records = read_routing_trace_jsonl(args.routing_trace)

    print("\n=== ROUTING TRACE RECORDS ===")
    for r in records:
        pprint(r)

    # --------------------------------------------------
    # Step 2: synthesize timing (inspection-only)
    # --------------------------------------------------
    timing_policy = TimingPolicy(
        epoch_origin_unix=args.epoch_origin_unix,
        epoch_duration_seconds=args.epoch_duration_seconds,
        spread_within_epoch_seconds=args.spread_within_epoch_seconds,
    )

    # --------------------------------------------------
    # Step 3: convert to interaction traces
    # --------------------------------------------------
    traces_by_user = build_interaction_traces(
        records=records,
        user_key=args.user_key,
        timing_policy=timing_policy,
    )

    print("\n=== INTERACTION TRACES ===")
    for user, trace in traces_by_user.items():
        print(f"\nUser: {user}")
        for event in trace:
            pprint(event)

    # --------------------------------------------------
    # Step 4: wrap into dataset
    # --------------------------------------------------
    dataset = BenignDataset(traces_by_user.values())

    print("\n=== BENIGN DATASET ===")
    print(f"num_traces = {len(dataset)}")
    for i, trace in enumerate(dataset.traces()):
        print(f"\nTrace {i}:")
        for event in trace:
            pprint(event)

    print("\n✔ Conversion inspection complete\n")


if __name__ == "__main__":
    main()
