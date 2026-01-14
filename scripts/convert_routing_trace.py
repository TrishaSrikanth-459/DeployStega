"""
scripts/convert_routing_trace.py

CLI utility:
- loads routing_trace.jsonl
- converts to InteractionTrace(s)
- prints summary counts

This does not write datasets to disk (you can add that later),
but it lets you confirm the conversion step is correct.
"""

from __future__ import annotations

import argparse

from dataset.routing_trace_to_interaction import TimingPolicy
from dataset.build_neighboring_dataset_from_routing import build_traces_from_routing_jsonl


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--routing-trace", required=True, help="Path to routing_trace.jsonl")
    ap.add_argument("--epoch-origin-unix", type=int, default=None)
    ap.add_argument("--epoch-duration-seconds", type=int, default=None)
    ap.add_argument("--spread-within-epoch-seconds", type=float, default=0.0)
    ap.add_argument("--user-key", default="role", choices=["role", "role_epoch"])
    args = ap.parse_args()

    timing_policy = None
    if args.epoch_origin_unix is not None or args.epoch_duration_seconds is not None:
        if args.epoch_origin_unix is None or args.epoch_duration_seconds is None:
            raise SystemExit("If you provide timing parameters, provide BOTH --epoch-origin-unix and --epoch-duration-seconds.")
        timing_policy = TimingPolicy(
            epoch_origin_unix=args.epoch_origin_unix,
            epoch_duration_seconds=args.epoch_duration_seconds,
            spread_within_epoch_seconds=args.spread_within_epoch_seconds,
        )

    traces = build_traces_from_routing_jsonl(
        routing_trace_path=args.routing_trace,
        timing_policy=timing_policy,
        user_key=args.user_key,
    )

    print("\n=== Conversion Summary ===")
    for user in sorted(traces.keys()):
        t = traces[user]
        print(f"{user}: num_events={len(t)}")
    print()


if __name__ == "__main__":
    main()
