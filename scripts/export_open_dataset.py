# scripts/export_open_dataset.py

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Any

from dataset.routing_trace_writer import load_routing_trace_jsonl
from dataset.routing_trace_to_interaction import build_interaction_traces


# ============================================================
# CLI
# ============================================================

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export DeployStega open interaction dataset (semantic embedded in event metadata)"
    )

    parser.add_argument(
        "--routing-trace",
        required=True,
        help="Path to routing_trace.jsonl (must include real timestamps; may include semantic content in metadata)",
    )

    parser.add_argument(
        "--out-dir",
        required=True,
        help="Output directory for released dataset",
    )

    parser.add_argument(
        "--label-users",
        required=True,
        help=(
            'REQUIRED. Comma-separated mapping like "0:covert,1:benign". '
            "Indices correspond to the order of exported user traces."
        ),
    )

    return parser.parse_args()


def _parse_user_labels(spec: str) -> Dict[int, str]:
    labels: Dict[int, str] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"Invalid --label-users entry (missing ':'): {part}")
        idx_str, lbl = part.split(":", 1)
        idx_str = idx_str.strip()
        lbl = lbl.strip().lower()

        if lbl not in ("benign", "covert"):
            raise ValueError(
                f"Invalid label '{lbl}' for user {idx_str}. Expected 'benign' or 'covert'."
            )

        try:
            idx = int(idx_str)
        except ValueError as e:
            raise ValueError(f"Invalid user index in --label-users: {idx_str}") from e

        if idx < 0:
            raise ValueError(f"User index must be >= 0, got {idx}")

        if idx in labels:
            raise ValueError(f"Duplicate label provided for user index {idx}")

        labels[idx] = lbl

    if not labels:
        raise ValueError("--label-users must not be empty")

    return labels


# ============================================================
# Main
# ============================================================

def main() -> None:
    args = _parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------
    # Load routing trace (authoritative source)
    # ------------------------------------------------------------
    records = load_routing_trace_jsonl(args.routing_trace)

    # IMPORTANT: timing_policy=None means "use record timestamps"
    traces_by_user = build_interaction_traces(
        records=records,
        timing_policy=None,  # REAL timestamps only
    )

    traces_list = list(traces_by_user.values())
    num_users = len(traces_list)

    # ------------------------------------------------------------
    # Labels are REQUIRED and must cover all users
    # ------------------------------------------------------------
    user_labels = _parse_user_labels(args.label_users)

    missing = [i for i in range(num_users) if i not in user_labels]
    extra = [i for i in user_labels.keys() if i >= num_users]
    if missing:
        raise ValueError(
            f"Missing labels for user indices: {missing}. "
            f"You must provide labels for ALL users 0..{num_users-1}."
        )
    if extra:
        raise ValueError(
            f"Labels provided for non-existent user indices: {extra}. "
            f"Dataset only has users 0..{num_users-1}."
        )

    # ------------------------------------------------------------
    # Export interaction dataset
    # ------------------------------------------------------------
    interaction_path = out_dir / "interaction_dataset.jsonl"
    total_events = 0

    with interaction_path.open("w", encoding="utf-8") as f:
        for user_idx, trace in enumerate(traces_list):
            # Fail-fast if timestamps are missing (you requested real timestamps)
            for ev in trace:
                if ev.timestamp is None:
                    raise ValueError(
                        "Encountered an InteractionEvent with timestamp=None. "
                        "Your routing trace must contain real timestamps."
                    )

            events: List[Dict[str, Any]] = []
            for ev in trace:
                events.append(
                    {
                        "timestamp": float(ev.timestamp),
                        "action_type": ev.action_type,
                        "artifact_ids": list(ev.artifact_ids),
                        # metadata is a tuple of pairs; convert to dict for the release
                        "metadata": dict(ev.metadata),
                    }
                )

            total_events += len(events)

            record = {
                "label": user_labels[user_idx],  # REQUIRED, never None
                "events": events,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------
    # Dataset index (clear + explicit)
    # ------------------------------------------------------------
    label_counts = {"benign": 0, "covert": 0}
    for lbl in user_labels.values():
        label_counts[lbl] += 1

    index = {
        "format_version": 1,
        "output_files": {
            "interaction_dataset": "interaction_dataset.jsonl",
            "dataset_index": "dataset_index.json",
        },
        "num_users": num_users,
        "num_events": total_events,
        "user_labels": {str(i): user_labels[i] for i in range(num_users)},
        "label_counts": label_counts,
        "label_schema": {
            "benign": "No covert communication is present in this user's trace.",
            "covert": "This user's trace contains covert activity by design (ground truth).",
        },
    }

    with (out_dir / "dataset_index.json").open("w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print("[OK] Dataset exported:")
    print(f" - {interaction_path}")
    print(f" - {out_dir / 'dataset_index.json'}")


if __name__ == "__main__":
    main()
