"""
scripts/view_adversary_dataset.py

Utility to materialize and inspect the adversary-visible dataset
constructed from routing traces.

This shows *exactly* what the adversary sees before feature extraction.
"""

from __future__ import annotations

import argparse
from typing import Dict

from dataset.routing_trace_record import read_routing_trace_jsonl
from dataset.routing_trace_to_interaction import build_interaction_traces


# ============================================================
# Timing policy definitions
# ============================================================

class TimingPolicy:
    """
    Base class for timestamp synthesis policies.
    """
    def __init__(self, epoch_origin_unix: float):
        self.epoch_origin_unix = epoch_origin_unix


class SynthesizeFromEpochPolicy(TimingPolicy):
    """
    Synthesizes timestamps deterministically from epoch index.
    """
    def __init__(self, epoch_origin_unix: float, epoch_duration_seconds: int = 60):
        super().__init__(epoch_origin_unix)
        self.epoch_duration_seconds = epoch_duration_seconds


def resolve_timing_policy(name: str) -> TimingPolicy:
    """
    Map CLI string to concrete TimingPolicy object.
    """
    if name == "synthesize_from_epoch":
        return SynthesizeFromEpochPolicy(
            epoch_origin_unix=1_768_400_000,  # fixed origin for reproducibility
            epoch_duration_seconds=60,
        )

    raise ValueError(f"Unknown timing policy: {name}")


# ============================================================
# CLI
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="View adversary-visible interaction dataset"
    )

    parser.add_argument(
        "--routing-trace",
        required=True,
        help="Path to routing_trace.jsonl",
    )

    parser.add_argument(
        "--timing-policy",
        default="synthesize_from_epoch",
        help="Timing synthesis policy",
    )

    args = parser.parse_args()

    # ------------------------------------------------------------
    # Load routing trace
    # ------------------------------------------------------------
    records = read_routing_trace_jsonl(args.routing_trace)

    # ------------------------------------------------------------
    # Resolve timing policy (THIS WAS MISSING)
    # ------------------------------------------------------------
    timing_policy = resolve_timing_policy(args.timing_policy)

    # ------------------------------------------------------------
    # Build adversary-visible traces
    # ------------------------------------------------------------
    traces_by_user = build_interaction_traces(
        records=records,
        timing_policy=timing_policy,
    )

    # ------------------------------------------------------------
    # Display dataset
    # ------------------------------------------------------------
    print("\n=== ADVERSARY-VISIBLE DATASET ===\n")

    for user_id, trace in traces_by_user.items():
        print(f"[User {user_id}]")
        for event in trace:
            print(
                f"  t={event.timestamp:.1f} | "
                f"{event.action_type} | "
                f"class={dict(event.metadata).get('artifact_class')} | "
                f"id={event.artifact_ids}"
            )
        print()


if __name__ == "__main__":
    main()
