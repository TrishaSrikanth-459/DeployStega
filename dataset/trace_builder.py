"""
dataset/trace_builder.py

Deterministically constructs InteractionTrace and BenignDataset objects
from routing trace logs.

This module performs NO inference, learning, or filtering.
It is a pure structural transformation layer.

Pipeline:
routing_trace.jsonl
  → RoutingTraceRecord
  → InteractionEvent
  → InteractionTrace
  → BenignDataset
"""

from __future__ import annotations

from typing import Dict

from dataset.benign_dataset import BenignDataset
from dataset.interaction_trace import InteractionTrace
from dataset.routing_trace_record import read_routing_trace_jsonl
from dataset.routing_trace_to_interaction import (
    TimingPolicy,
    build_interaction_traces,
)


class TraceBuilder:
    """
    Canonical dataset builder for routing-trace-based experiments.

    This class exists to provide a *single, obvious entry point*
    for converting routing traces into datasets.
    """

    @staticmethod
    def from_routing_trace_jsonl(
        *,
        path: str,
        timing_policy: TimingPolicy | None = None,
        user_key: str = "role",
    ) -> BenignDataset:
        """
        Build a BenignDataset from a routing_trace.jsonl file.

        Parameters
        ----------
        path:
            Path to routing_trace.jsonl
        timing_policy:
            Required if routing records do not include timestamps
        user_key:
            How to group users ("role" or "role_epoch")

        Returns
        -------
        BenignDataset
        """
        # 1) Load routing trace records
        records = read_routing_trace_jsonl(path)

        # 2) Convert to InteractionTraces
        traces_by_user: Dict[str, InteractionTrace] = build_interaction_traces(
            records=records,
            user_key=user_key,
            timing_policy=timing_policy,
        )

        if not traces_by_user:
            raise ValueError("No interaction traces constructed from routing trace")

        # 3) Deterministic ordering of users
        traces = [traces_by_user[user] for user in sorted(traces_by_user.keys())]

        return BenignDataset(traces)
