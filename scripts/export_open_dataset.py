from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Any

from dataset.routing_trace_writer import load_routing_trace_jsonl
from dataset.routing_trace_to_interaction import build_interaction_traces


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export DeployStega open interaction dataset (semantic embedded in routing trace)"
    )
    parser.add_argument("--routing-trace", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--label-users", default="", help='Comma-separated mapping like "0:covert,1:benign"')
    return parser.parse_args()


def _parse_user_labels(spec: str) -> Dict[int, str]:
    labels: Dict[int, str] = {}
    if not spec.strip():
        return labels
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        idx_s, lbl = part.split(":", 1)
        labels[int(idx_s.strip())] = lbl.strip()
    return labels


def main() -> None:
    args = _parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records = load_routing_trace_jsonl(args.routing_trace)
    traces_by_user = build_interaction_traces(records=records, timing_policy=None)

    user_labels = _parse_user_labels(args.label_users)

    # deterministic user order (keys sorted)
    users = sorted(traces_by_user.keys())

    interaction_path = out_dir / "interaction_dataset.jsonl"
    total_events = 0

    user_index_to_label: Dict[str, Any] = {}
    with interaction_path.open("w", encoding="utf-8") as f:
        for user_idx, user in enumerate(users):
            trace = traces_by_user[user]

            label = user_labels.get(user_idx)
            user_index_to_label[str(user_idx)] = {"user_key": user, "label": label}

            events = []
            for ev in trace:
                events.append(
                    {
                        "timestamp": ev.timestamp,
                        "action_type": ev.action_type,
                        "artifact_ids": list(ev.artifact_ids),
                        # keep everything adversary-visible + semantic embedded
                        "metadata": dict(ev.metadata),
                    }
                )

            total_events += len(events)

            f.write(
                json.dumps(
                    {
                        "user_index": user_idx,
                        "user_key": user,
                        "label": label,
                        "events": events,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    # label counts
    counts: Dict[str, int] = {}
    for idx, lbl in user_labels.items():
        counts[lbl] = counts.get(lbl, 0) + 1

    index = {
        "num_users": len(users),
        "num_traces": len(users),
        "num_events": total_events,

        # Clear labeling info
        "label_spec": args.label_users,
        "user_index_to_label": user_index_to_label,
        "label_counts": counts,
    }

    with (out_dir / "dataset_index.json").open("w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)

    print("[OK] Dataset exported:")
    print(f" - {interaction_path}")
    print(f" - {out_dir / 'dataset_index.json'}")


if __name__ == "__main__":
    main()
