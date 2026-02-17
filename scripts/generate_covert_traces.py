#!/usr/bin/env python3
"""
Batch covert trace generator for DeployStega.

Reads a directory of plaintext secret files (one per secret) and generates
a corresponding covert trace for each. Each trace is saved as a JSONL file
containing the sequence of steganographic events (one per chunk) with
realistic timestamps.

This script is intentionally simpler than the interactive_dead_drop.py because:
- It does not simulate real‑time epoch progression.
- It does not use a resolver or feasibility region (dummy identifiers/URLs are used).
- It does not handle receiver logic or identity verification.
- It generates all chunks of a secret in one file (no inter‑epoch waiting).

Usage:
    python generate_covert_traces.py --secrets-dir /path/to/secrets/ \\
                                     --output-dir /path/to/covert_traces/ \\
                                     [--num-traces N] [--workers 4] [--seed 42] \\
                                     [--start-time 1700000000] [--gap-mean 3600]
"""

import json
import sys
import time
import random
import argparse
from pathlib import Path
from typing import List, Optional
import concurrent.futures
import functools
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from routing.semantic.stego_encoder import ByteLevelStegoEncoder
from scripts.experiment_context import load_experiment_context


def generate_timestamps(num_events: int, start_time: float, mean_gap: float) -> List[float]:
    """Generate timestamps with exponential gaps."""
    gaps = np.random.exponential(scale=mean_gap, size=num_events)
    timestamps = [start_time + sum(gaps[:i+1]) for i in range(num_events)]
    return timestamps


def normalize_plans(raw, default_artifact_class: str) -> List[dict]:
    """Same as in interactive_dead_drop.py."""
    if isinstance(raw, str):
        return [{"artifact_class": default_artifact_class, "stego_text": raw}]
    if isinstance(raw, list):
        out = []
        for p in raw:
            if not isinstance(p, dict):
                raise TypeError(f"plan must be dict, got {type(p)}")
            ac = p.get("artifact_class", default_artifact_class)
            st = p.get("stego_text", "")
            out.append({"artifact_class": ac, "stego_text": st})
        return out
    raise TypeError(f"Unsupported type: {type(raw)}")


def encode_secret_message_wrapper(encoder: ByteLevelStegoEncoder,
                                   secret_message: str,
                                   artifact_class: str,
                                   artifact_context: dict) -> List[dict]:
    """Simplified version of encode_secret_message (without epoch)."""
    context = {
        "repo_context": artifact_context.get("text", "authentication system")[:100],
        "file_context": f"{artifact_class}/batch"
    }
    chunks = encoder.encode(secret_message, context, positions_filename=None)
    plans = [{"artifact_class": artifact_class, "stego_text": chunk} for chunk in chunks]
    return plans


def process_one_secret(secret_text: str, secret_id: str, output_dir: Path,
                       encoder: ByteLevelStegoEncoder,
                       artifact_class: str, artifact_context: dict,
                       start_time: float, gap_mean: float) -> Optional[Path]:
    """
    Encode a single secret and write its trace to a JSONL file.
    Returns the path to the output file on success, None on failure.
    """
    try:
        # Encode the secret into chunks
        plans = encode_secret_message_wrapper(encoder, secret_text, artifact_class, artifact_context)
        chunks = [plan["stego_text"] for plan in plans]

        # Generate timestamps for each event
        timestamps = generate_timestamps(len(chunks), start_time, gap_mean)

        # Build events
        events = []
        for i, chunk in enumerate(chunks):
            event = {
                "experiment_id": f"covert_{secret_id}",
                "epoch": i,  # simple epoch = chunk index
                "role": "sender",
                "artifact_class": artifact_class,
                "identifier": ["dummy_owner", "dummy_repo", i+1],  # dummy, replace with real resolver if needed
                "url": f"https://github.com/dummy_owner/dummy_repo",
                "semantic_text": chunk,
                "semantic_meaning": None,
                "semantic_ref": None,
                "semantic_label": "explicit_testing_payload",
                "semantic_content_type": "TokenBinning_ExplicitTesting",
                "timestamp": timestamps[i]
            }
            events.append(event)

        # Write to output file
        out_file = output_dir / f"trace_{secret_id}.jsonl"
        with open(out_file, "w") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")
        return out_file

    except Exception as e:
        print(f"Error processing secret {secret_id}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Batch covert trace generator")
    parser.add_argument("--secrets-dir", required=True,
                        help="Directory containing one secret message per file")
    parser.add_argument("--output-dir", required=True,
                        help="Directory where trace files will be saved")
    parser.add_argument("--num-traces", type=int, default=None,
                        help="Number of traces to generate (if less than total secrets, random sample)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Number of parallel workers")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility")
    parser.add_argument("--start-time", type=float, default=1700000000,
                        help="Base timestamp for first event (Unix seconds)")
    parser.add_argument("--gap-mean", type=float, default=3600,
                        help="Mean gap between events (seconds)")
    parser.add_argument("--artifact-class", default="Issue",
                        help="Default artifact class for steganographic events")
    args = parser.parse_args()

    np.random.seed(args.seed)
    random.seed(args.seed)

    secrets_dir = Path(args.secrets_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Gather secret files
    secret_files = sorted(secrets_dir.glob("*"))
    if not secret_files:
        print(f"No files found in {secrets_dir}")
        return

    # If num-traces specified, randomly select that many
    if args.num_traces is not None:
        if args.num_traces > len(secret_files):
            print(f"Warning: --num-traces ({args.num_traces}) > total files ({len(secret_files)}). Using all files.")
        else:
            secret_files = random.sample(secret_files, args.num_traces)

    print(f"Generating {len(secret_files)} traces...")

    # Initialize encoder (quiet mode)
    encoder = ByteLevelStegoEncoder(quiet=True)

    # Dummy artifact context (can be extended later)
    artifact_context = {
        "text": "dummy repository context"
    }

    # Process secrets in parallel
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for i, fpath in enumerate(secret_files):
            secret_id = f"{i:06d}"
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    secret_text = f.read().strip()
                if not secret_text:
                    print(f"Warning: empty file {fpath}, skipping")
                    continue
                future = executor.submit(
                    process_one_secret,
                    secret_text,
                    secret_id,
                    output_dir,
                    encoder,
                    args.artifact_class,
                    artifact_context,
                    args.start_time,
                    args.gap_mean
                )
                futures[future] = secret_id
            except Exception as e:
                print(f"Error reading {fpath}: {e}")

        for future in concurrent.futures.as_completed(futures):
            secret_id = futures[future]
            out_path = future.result()
            if out_path:
                print(f"Generated {out_path}")
                results.append(str(out_path))
            else:
                print(f"Failed for secret {secret_id}")

    print(f"\nDone. Generated {len(results)} traces in {output_dir}")


if __name__ == "__main__":
    main()
