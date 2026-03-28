#!/usr/bin/env python3
"""
Batch covert trace generator for DeployStega.
Fixed version with proper multiprocessing support and directory creation.
"""

import json
import sys
import os
import random
import argparse
from pathlib import Path
from typing import List, Optional
import concurrent.futures
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from routing.dead_drop_function.dead_drop_resolver import DeadDropResolver
from routing.dead_drop_function.repository_snapshot.serializer import read_snapshot
from routing.dead_drop_function.trace_weighted_feasibility import (
    AllowAllFeasibilityRegion,
    TraceBasedFeasibilityRegion,
    PrecomputedFeasibilityRegion
)
from scripts.experiment_context import load_experiment_context


# ----------------------------------------------------------------------
# Simple timestamp generator
# ----------------------------------------------------------------------
def generate_timestamps(num_events: int, start_time: float, mean_gap: float) -> List[float]:
    """Generate timestamps with exponential gaps."""
    gaps = np.random.exponential(scale=mean_gap, size=num_events)
    timestamps = [start_time + sum(gaps[:i+1]) for i in range(num_events)]
    return timestamps


# ----------------------------------------------------------------------
# Encode secret wrapper (to be called inside worker)
# ----------------------------------------------------------------------
def encode_secret_message_in_worker(secret_message: str,
                                     artifact_class: str,
                                     artifact_context: dict,
                                     openai_api_key: str) -> List[str]:
    """
    Create encoder and encode secret. This runs inside the worker process.
    """
    # Set API key for this process
    os.environ['OPENAI_API_KEY'] = openai_api_key
    
    # Import here to avoid pickling issues
    from routing.semantic.stego_encoder import ByteLevelStegoEncoder
    
    context = {
        "repo_context": artifact_context.get("text", "authentication system")[:100],
        "file_context": f"{artifact_class}/batch"
    }
    
    encoder = ByteLevelStegoEncoder(quiet=False)
    chunks = encoder.encode(secret_message, context, positions_filename=None)
    return chunks


# ----------------------------------------------------------------------
# Process one secret (runs in worker process)
# ----------------------------------------------------------------------
def process_one_secret(secret_text: str, 
                       secret_id: str, 
                       output_dir_str: str,
                       resolver_data: dict,  # Serialized resolver data
                       artifact_context: dict,
                       start_time: float, 
                       gap_mean: float,
                       sender_id: str, 
                       receiver_id: str,
                       openai_api_key: str,
                       owner: str,
                       repo: str) -> Optional[str]:
    """
    Encode a single secret and write its trace to a JSONL file.
    This runs in a separate process.
    """
    try:
        output_dir = Path(output_dir_str)
        
        # Recreate resolver from serialized data
        from routing.dead_drop_function.dead_drop_resolver import DeadDropResolver
        from routing.dead_drop_function.repository_snapshot.serializer import read_snapshot
        
        # Load snapshot from the serialized data
        snapshot = read_snapshot(resolver_data['snapshot_path'])
        
        # Recreate feasibility region
        feasibility = None
        if resolver_data.get('feasibility_allow'):
            feasibility = PrecomputedFeasibilityRegion(
                resolver_data['feasibility_allow'], 
                resolver_data.get('feasibility_weights')
            )
        elif resolver_data.get('feasibility_dir'):
            feasibility = TraceBasedFeasibilityRegion(resolver_data['feasibility_dir'])
        else:
            feasibility = AllowAllFeasibilityRegion()
        
        resolver = DeadDropResolver(
            snapshot=snapshot,
            feasibility_region=feasibility,
            owner=owner,
            repo=repo,
        )
        
        # Encode the secret into chunks
        chunks = encode_secret_message_in_worker(
            secret_text, "dummy", artifact_context, openai_api_key
        )
        num_events = len(chunks)
        
        print(f"  Secret {secret_id}: encoded into {num_events} chunks")
        
        # Generate timestamps
        timestamps = generate_timestamps(num_events, start_time, gap_mean)
        
        # Build events, one per chunk
        events = []
        for i, chunk in enumerate(chunks):
            # Use resolver to get artifact class and URL for this "epoch" (i)
            try:
                result = resolver.resolve(epoch=i, sender_id=sender_id, 
                                         receiver_id=receiver_id, role="sender")
                artifact_class = result["artifactClass"]
                identifier = result["identifier"]
                url = result["url"]
            except Exception as e:
                print(f"  Resolver failed for epoch {i} on secret {secret_id}: {e}")
                # Fallback to dummy
                artifact_class = "Issue"
                identifier = ("dummy_owner", "dummy_repo", i+1)
                url = f"https://github.com/dummy_owner/dummy_repo/issues/{i+1}"
            
            event = {
                "experiment_id": f"covert_{secret_id}",
                "epoch": i,
                "role": "sender",
                "artifact_class": artifact_class,
                "identifier": list(identifier) if isinstance(identifier, tuple) else identifier,
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
        
        print(f"  ✓ Generated {out_file}")
        return str(out_file)
        
    except Exception as e:
        print(f"  ✗ Error processing secret {secret_id}: {e}")
        import traceback
        traceback.print_exc()
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
    parser.add_argument("--feasibility-dir", type=str, default=None,
                        help="Path to benign traces directory (to build feasibility region from traces)")
    parser.add_argument("--feasibility-allow", type=str, default=None,
                        help="Path to allow_by_epoch.json (pre-computed feasibility patterns)")
    parser.add_argument("--feasibility-weights", type=str, default=None,
                        help="Path to weight_by_epoch.json (optional, for pre-computed feasibility)")
    parser.add_argument("--num-traces", type=int, default=None,
                        help="Number of traces to generate (if less than total secrets, random sample)")
    parser.add_argument("--workers", type=int, default=1,  # Changed default to 1 for stability
                        help="Number of parallel workers (use 1 for debugging)")
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
    
    # Create output directory immediately
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_dir}")
    
    np.random.seed(args.seed)
    random.seed(args.seed)
    
    # Check for OpenAI API key
    openai_api_key = os.environ.get('OPENAI_API_KEY', '')
    if not openai_api_key:
        print("ERROR: OPENAI_API_KEY environment variable not set!")
        print("Please set it with: export OPENAI_API_KEY='your-key-here'")
        sys.exit(1)
    print("✓ OpenAI API key found")
    
    # Load experiment context to get sender/receiver IDs
    try:
        ctx = load_experiment_context(args.manifest)
        sender_id = ctx.sender_id
        receiver_id = ctx.receiver_id
        print(f"✓ Loaded sender: {sender_id}, receiver: {receiver_id}")
    except Exception as e:
        print(f"Warning: could not load manifest, using dummy IDs: {e}")
        sender_id = "dummy_sender"
        receiver_id = "dummy_receiver"
    
    # Load snapshot
    try:
        snapshot = read_snapshot(args.snapshot)
        print(f"✓ Loaded snapshot from {args.snapshot}")
    except Exception as e:
        print(f"Error loading snapshot: {e}")
        sys.exit(1)
    
    # Infer owner and repo from first artifact
    owner = None
    repo = None
    for cls in snapshot.artifact_classes():
        arts = snapshot.artifacts_of(cls)
        if arts:
            owner, repo = arts[0].identifier[:2]
            break
    
    if not owner or not repo:
        raise RuntimeError("Cannot infer repository identity from snapshot")
    print(f"✓ Repository: {owner}/{repo}")
    
    # Prepare resolver data for workers (serializable)
    resolver_data = {
        'snapshot_path': args.snapshot,
        'feasibility_dir': args.feasibility_dir,
        'feasibility_allow': args.feasibility_allow,
        'feasibility_weights': args.feasibility_weights,
    }
    
    # Build feasibility region (just for validation, not passed directly)
    if args.feasibility_allow:
        print(f"✓ Using pre-computed feasibility from {args.feasibility_allow}")
    elif args.feasibility_dir:
        print(f"✓ Loading feasibility region from benign traces in {args.feasibility_dir}")
    else:
        print("✓ No feasibility provided, using AllowAllFeasibilityRegion")
    
    # Gather secret files
    secrets_dir = Path(args.secrets_dir)
    secret_files = sorted(secrets_dir.glob("*.txt"))
    if not secret_files:
        print(f"No .txt files found in {secrets_dir}")
        return
    
    # If num-traces specified, randomly select that many
    if args.num_traces is not None:
        if args.num_traces > len(secret_files):
            print(f"Warning: --num-traces ({args.num_traces}) > total files ({len(secret_files)}). Using all files.")
        else:
            secret_files = random.sample(secret_files, args.num_traces)
    
    print(f"\n📊 Generating {len(secret_files)} traces with {args.workers} workers...")
    print("=" * 60)
    
    # Dummy artifact context
    artifact_context = {
        "text": "dummy repository context"
    }
    
    # Process secrets
    results = []
    successful = 0
    failed = 0
    
    # Use ThreadPoolExecutor instead of ProcessPoolExecutor to avoid pickling issues
    # Threads work better with API calls and share memory space
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for i, fpath in enumerate(secret_files):
            secret_id = f"{i:06d}"
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    secret_text = f.read().strip()
                if not secret_text:
                    print(f"⚠ Warning: empty file {fpath}, skipping")
                    continue
                
                future = executor.submit(
                    process_one_secret,
                    secret_text,
                    secret_id,
                    str(output_dir),
                    resolver_data,
                    artifact_context,
                    args.start_time,
                    args.gap_mean,
                    sender_id,
                    receiver_id,
                    openai_api_key,
                    owner,
                    repo
                )
                futures[future] = secret_id
            except Exception as e:
                print(f"Error reading {fpath}: {e}")
                failed += 1
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(futures):
            secret_id = futures[future]
            try:
                out_path = future.result(timeout=300)  # 5 minute timeout per secret
                if out_path:
                    results.append(out_path)
                    successful += 1
                else:
                    failed += 1
                    print(f"✗ Failed for secret {secret_id}")
            except concurrent.futures.TimeoutError:
                print(f"✗ Timeout for secret {secret_id}")
                failed += 1
            except Exception as e:
                print(f"✗ Exception for secret {secret_id}: {e}")
                failed += 1
    
    # Summary
    print("=" * 60)
    print(f"\n✅ Done!")
    print(f"   Successful: {successful}")
    print(f"   Failed: {failed}")
    print(f"   Total traces: {len(results)}")
    print(f"   Output directory: {output_dir}")
    
    # Save summary
    summary_file = output_dir / "generation_summary.json"
    with open(summary_file, "w") as f:
        json.dump({
            "total_secrets": len(secret_files),
            "successful": successful,
            "failed": failed,
            "traces": results,
            "parameters": {
                "workers": args.workers,
                "seed": args.seed,
                "start_time": args.start_time,
                "gap_mean": args.gap_mean
            }
        }, f, indent=2)
    print(f"   Summary saved to: {summary_file}")


if __name__ == "__main__":
    main()
