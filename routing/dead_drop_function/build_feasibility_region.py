#!/usr/bin/env python3
"""
Build feasibility region data from synthetic benign traces.

This script reads a directory of per‑user JSONL trace files and computes:
- For each epoch, role, artifact_class: set of allowed URLs (allowlist).
- For each epoch, role, artifact_class: weight (frequency) of each URL.

Outputs two JSON files: allow_by_epoch.json and weight_by_epoch.json,
which can be loaded by PrecomputedFeasibilityRegion.
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict, Counter

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", required=True,
                        help="Directory containing per‑user JSONL trace files")
    parser.add_argument("--output-dir", required=True,
                        help="Directory to save output JSON files")
    parser.add_argument("--roles", nargs="+", default=["user"],
                        help="Roles present in traces (default: user)")
    return parser.parse_args()

def main():
    args = parse_args()
    trace_dir = Path(args.trace_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Structure: counts[epoch][role][artifact_class][url] = count
    counts = defaultdict(lambda: defaultdict(lambda: defaultdict(Counter)))

    trace_files = sorted(trace_dir.glob("*.jsonl"))
    print(f"Found {len(trace_files)} trace files.")

    for fpath in trace_files:
        with open(fpath) as f:
            for line in f:
                if not line.strip():
                    continue
                ev = json.loads(line)
                epoch = ev["epoch"]          # use as is (event index)
                role = ev["role"]             # "user"
                artifact_class = ev["artifact_class"]
                url = ev["url"]
                counts[epoch][role][artifact_class][url] += 1

    # Build allowlist and weight dictionaries
    allow_by_epoch = {}
    weight_by_epoch = {}

    for epoch, role_dict in counts.items():
        allow_by_epoch[epoch] = {}
        weight_by_epoch[epoch] = {}
        for role, class_dict in role_dict.items():
            allow_by_epoch[epoch][role] = {}
            weight_by_epoch[epoch][role] = {}
            for cls, url_counter in class_dict.items():
                urls = list(url_counter.keys())
                allow_by_epoch[epoch][role][cls] = urls
                # weights are the raw counts (can be normalized later if desired)
                weight_by_epoch[epoch][role][cls] = dict(url_counter)

    # Save
    with open(out_dir / "allow_by_epoch.json", "w") as f:
        json.dump(allow_by_epoch, f, indent=2)
    with open(out_dir / "weight_by_epoch.json", "w") as f:
        json.dump(weight_by_epoch, f, indent=2)

    print(f"Allowlist saved to {out_dir / 'allow_by_epoch.json'}")
    print(f"Weights saved to {out_dir / 'weight_by_epoch.json'}")

if __name__ == "__main__":
    main()
