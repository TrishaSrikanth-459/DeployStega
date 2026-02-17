#!/usr/bin/env python3
"""
Batch covert trace generator for DeployStega.

Reads a directory of plaintext secret files (one per secret) and generates
a corresponding covert trace for each. Each trace is saved as a JSONL file
containing the sequence of steganographic events (one per chunk) with
realistic timestamps.

This script uses the same core components as interactive_dead_drop.py:
- A dummy feasibility region (AllowAllFeasibility)
- A resolver to pick artifact class and URL for each event
- The steganography encoder to generate chunks
- A simple timestamp generator (replace with behavioral sampler later)

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
from typing import List, Optional, Tuple
import concurrent.futures
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from routing.semantic.stego_encoder import ByteLevelStegoEncoder
from routing.dead_drop_function.dead_drop_resolver import DeadDropResolver
from routing.dead_drop_function.repository_snapshot.serializer import read_snapshot
from routing.dead_drop_function.feasibility_region import FeasibilityRegion, AllowAllFeasibilityRegion
from scripts.experiment_context import load_experiment_context
from dataset.routing_trace_record import RoutingTraceRecord
from dataset.routing_trace_to_interaction import TimingPolicy, build_interaction_traces


# ----------------------------------------------------------------------
# Simple timestamp generator (replace with behavioral sampler later)
# ----------------------------------------------------------------------
def generate_timestamps(num_events: int, start_time: float, mean_gap: float) -> List[float]:
    """Generate timestamps with exponential gaps."""
    gaps = np.random.exponential(scale=mean_gap, size=num_events)
    timestamps = [start_time + sum(gaps[:i+1]) for i in range(num_events)]
    return timestamps


# ----------------------------------------------------------------------
# Normalize plans (same as interactive script)
# ----------------------------------------------------------------------
def normalize_plans(raw, default_artifact_class: str) -> List[dict]:
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


# ----------------------------------------------------------------------
# Wrapper for encoder (simplified)
# ----------------------------------------------------------------------
def encode_secret_message_wrapper(encoder: ByteLevelStegoEncoder,
                                   secret_message: str,
                                   artifact_class: str,
                                   artifact_context: dict) -> List[dict]:
    context = {
        "repo_context": artifact_context.get("text", "authentication system")[:100],
        "file_context": f"{artifact_class}/batch"
    }
    chunks = encoder.encode(secret_message, context, positions_filename=None)
    plans = [{"artifact_class": artifact_class, "stego_text": chunk} for chunk in chunks]
    return plans


# ----------------------------------------------------------------------
# Process one secret
# ----------------------------------------------------------------------
def process_one_secret(secret_text: str, secret_id: str, output_dir: Path,
                       encoder: ByteLevelStegoEncoder,
                       resolver: DeadDropResolver,
                       artifact_context: dict,
                       start_time: float, gap_mean: float,
                       sender_id: str, receiver_id: str) -> Optional[Path]:
    """
    Encode a single secret and write its trace to a JSONL file.
    Uses the resolver to generate a realistic artifact class and URL for each chunk.
    """
    try:
        # Encode the secret into chunks (determines number of events)
        plans = encode_secret_message_wrapper(encoder, secret_text, "dummy", artifact_context)
        chunks = [plan["stego_text"] for plan in plans]
        num_events = len(chunks)

        # Generate timestamps
        timestamps = generate_timestamps(num_events, start_time, gap_mean)

        # Build events, one per chunk
        events = []
        for i, chunk in enumerate(chunks):
            # Use resolver to get artifact class and URL for this "epoch" (i)
            # We pass sender_id and receiver_id as given (same for all)
            try:
                result = resolver.resolve(epoch=i, sender_id=sender_id, receiver_id=receiver_id, role="sender")
                artifact_class = result["artifactClass"]
                identifier = result["identifier"]
                url = result["url"]
            except Exception as e:
                # Fallback to dummy if resolver fails (should not happen with AllowAll)
                artifact_class = "Issue"
                identifier = ["dummy_owner", "dummy_repo", i+1]
                url = f"https://github.com/dummy_owner/dummy_repo/issues/{i+1}"

            event = {
                "experiment_id": f"covert_{secret_id}",
                "epoch": i,
                "role": "sender",
                "artifact_class": artifact_class,
                "identifier": identifier,
                "url": url,
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


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
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
    parser.add_argument("--snapshot", type=str, default="experiments/snapshot.json",
                        help="Path to snapshot JSON file")
    parser.add_argument("--manifest", type=str, default="experiments/experiment_manifest.json",
                        help="Path to experiment manifest (to get sender/receiver IDs)")
    args = parser.parse_args()

    np.random.seed(args.seed)
    random.seed(args.seed)

    # Load experiment context to get sender/receiver IDs (or use dummies)
    try:
        ctx = load_experiment_context(args.manifest)
        sender_id = ctx.sender_id
        receiver_id = ctx.receiver_id
    except Exception as e:
        print(f"Warning: could not load manifest, using dummy IDs: {e}")
        sender_id = "dummy_sender"
        receiver_id = "dummy_receiver"

    # Build resolver with dummy feasibility region
    try:
        snapshot = read_snapshot(args.snapshot)
    except Exception as e:
        print(f"Error loading snapshot: {e}")
        sys.exit(1)

    # Dummy feasibility region (allows everything)
    feasibility = AllowAllFeasibilityRegion()

    # Infer owner and repo from first artifact
    for cls in snapshot.artifact_classes():
        arts = snapshot.artifacts_of(cls)
        if arts:
            owner, repo = arts[0].identifier[:2]
            break
    else:
        raise RuntimeError("Cannot infer repository identity from snapshot")

    resolver = DeadDropResolver(
        snapshot=snapshot,
        feasibility_region=feasibility,
        owner=owner,
        repo=repo,
    )

    # Gather secret files
    secrets_dir = Path(args.secrets_dir)
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

    # Dummy artifact context (will be overridden by resolver results)
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
                    Path(args.output_dir),
                    encoder,
                    resolver,
                    artifact_context,
                    args.start_time,
                    args.gap_mean,
                    sender_id,
                    receiver_id
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

    print(f"\nDone. Generated {len(results)} traces in {args.output_dir}")


if __name__ == "__main__":
    main()
