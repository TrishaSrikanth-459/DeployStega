
"""
Resumable Hugging Face extraction with checkpoint support.
"""
import json
import pickle
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, Set, Tuple
import gc
import sys
import os


REPO_ROOT = Path(__file__).resolve().parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.chdir(REPO_ROOT)

print(f"✓ Working directory: {os.getcwd()}")
print(f"✓ Python path includes repo root")
print()

try:
    from datasets import load_dataset
except ImportError:
    print("Installing datasets library...")
    import subprocess
    subprocess.check_call(["pip", "install", "datasets"])
    from datasets import load_dataset

# Import dataset classes
from dataset.interaction_event import InteractionEvent
from dataset.interaction_trace import InteractionTrace
from dataset.benign_dataset import BenignDataset

# Import feature extractors
from features.behavioral.timing import TimingFeatureExtractor
from features.behavioral.session import SessionFeatureExtractor
from features.behavioral.transition import TransitionFeatureExtractor
from features.behavioral.frequency import FrequencyFeatureExtractor
from features.behavioral.revisit import RevisitFeatureExtractor

# Import config
from config import (
    ROUTING_NAMESPACE,
    MIN_EVENTS_PER_USER,
    OUTPUT_JSON_PATH
)

# Configuration
MAX_EVENTS_PER_USER = 50000
BATCH_SIZE = 10000
CHECKPOINT_INTERVAL = 200  # Save every 200 batches (2M events)
CHECKPOINT_FILE = Path("hf_extraction_checkpoint.pkl")


def _get_metadata_value(event_data: Dict, key: str):
    """Extract artifact_class from GitHub event data."""
    event_type = event_data.get("type", "")

    event_to_class = {
        'IssuesEvent': 'Issue',
        'PullRequestEvent': 'PullRequest',
        'PushEvent': 'Commit',
        'CreateEvent': 'Commit',
        'IssueCommentEvent': 'IssueComment',
        'PullRequestReviewEvent': 'PullRequestComment',
        'PullRequestReviewCommentEvent': 'PullRequestComment',
        'CommitCommentEvent': 'CommitComment'
    }

    if key == "artifact_class":
        return event_to_class.get(event_type, event_type)
    return None


def save_checkpoint(user_events: Dict, batches_processed: int, 
                   total_events: int, namespace_events: int):
    """Save checkpoint to disk."""
    checkpoint_data = {
        'user_events': dict(user_events),
        'batches_processed': batches_processed,
        'total_events': total_events,
        'namespace_events': namespace_events,
        'timestamp': datetime.now().isoformat()
    }
    
    # Atomic save
    temp_file = CHECKPOINT_FILE.with_suffix('.tmp')
    with open(temp_file, 'wb') as f:
        pickle.dump(checkpoint_data, f)
    temp_file.replace(CHECKPOINT_FILE)
    
    return CHECKPOINT_FILE


def load_checkpoint() -> Tuple[Dict, int, int, int]:
    """Load checkpoint from disk if it exists."""
    if not CHECKPOINT_FILE.exists():
        return defaultdict(list), 0, 0, 0
    
    try:
        with open(CHECKPOINT_FILE, 'rb') as f:
            checkpoint_data = pickle.load(f)
        
        print("=" * 70)
        print("CHECKPOINT FOUND - RESUMING")
        print("=" * 70)
        print(f"Checkpoint from: {checkpoint_data['timestamp']}")
        print(f"Users loaded: {len(checkpoint_data['user_events']):,}")
        print(f"Batches processed: {checkpoint_data['batches_processed']}")
        print(f"Total events: {checkpoint_data['total_events']:,}")
        print(f"Namespace events: {checkpoint_data['namespace_events']:,}")
        print("=" * 70)
        print()
        
        user_events = defaultdict(list, checkpoint_data['user_events'])
        return (user_events, 
                checkpoint_data['batches_processed'],
                checkpoint_data['total_events'],
                checkpoint_data['namespace_events'])
    
    except Exception as e:
        print(f"Warning: Could not load checkpoint: {e}")
        print("Starting fresh...")
        return defaultdict(list), 0, 0, 0


def clear_checkpoint():
    """Remove checkpoint file after successful completion."""
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print(f"✓ Removed checkpoint file")


def load_gharchive_from_huggingface(
    dataset_name: str = "shivank21/gh_archive_june_week1",
    resume: bool = True
) -> BenignDataset:
    """Load GitHub Archive data from Hugging Face dataset with checkpointing."""
    
    print("=" * 70)
    print("LOADING GITHUB ARCHIVE DATA FROM HUGGING FACE (RESUMABLE)")
    print("=" * 70)
    print(f"Dataset: {dataset_name}")
    print(f"Routing namespace: {len(ROUTING_NAMESPACE)} event types")
    print(f"Min events per user: {MIN_EVENTS_PER_USER}")
    print(f"Max events per user: {MAX_EVENTS_PER_USER}")
    print(f"Checkpoint interval: every {CHECKPOINT_INTERVAL} batches")
    print()

    # Load checkpoint if resuming
    if resume:
        user_events, batches_to_skip, total_events, namespace_events = load_checkpoint()
    else:
        user_events = defaultdict(list)
        batches_to_skip = 0
        total_events = 0
        namespace_events = 0

    print("Loading dataset...")
    try:
        dataset = load_dataset(dataset_name, split="train", streaming=True)
        print("✓ Dataset loaded (streaming mode)")
        print()
    except Exception as e:
        print(f"✗ Error loading dataset: {e}")
        raise

    batch_num = 0
    
    print(f"Processing events (will skip first {batches_to_skip} batches)...")
    print()

    # Process in batches
    for batch in dataset.iter(batch_size=BATCH_SIZE):
        batch_num += 1
        
        # Skip already processed batches
        if batch_num <= batches_to_skip:
            if batch_num % 500 == 0:
                print(f"  Skipping batch {batch_num}...")
            continue
        
        batch_namespace_events = 0

        # Process each event in the batch
        for i in range(len(batch['id'])):
            try:
                event_type = batch['type'][i]
                total_events += 1

                if event_type not in ROUTING_NAMESPACE:
                    continue

                actor = batch['actor'][i]
                if actor is None or 'id' not in actor:
                    continue
                user_id = actor['id']

                if len(user_events[user_id]) >= MAX_EVENTS_PER_USER:
                    continue

                repo = batch['repo'][i]
                if repo is None or 'id' not in repo:
                    continue
                repo_id = repo['id']

                timestamp_str = batch['created_at'][i]
                if timestamp_str:
                    timestamp = datetime.fromisoformat(
                        str(timestamp_str).replace("Z", "+00:00")
                    ).timestamp()
                else:
                    continue

                artifact_class = _get_metadata_value({'type': event_type}, "artifact_class")

                interaction_event = InteractionEvent(
                    timestamp=timestamp,
                    action_type=event_type,
                    artifact_ids=(repo_id,),
                    metadata=(("artifact_class", artifact_class),)
                )

                user_events[user_id].append(interaction_event)
                batch_namespace_events += 1
                namespace_events += 1

            except (KeyError, TypeError, ValueError):
                continue

        # Progress update every 50 batches
        if batch_num % 50 == 0:
            pct = (namespace_events / max(total_events, 1)) * 100
            print(f"  Batch {batch_num}: {total_events:,} total ({namespace_events:,} / {pct:.1f}% in namespace), {len(user_events):,} users")

        # Save checkpoint periodically
        if batch_num % CHECKPOINT_INTERVAL == 0:
            checkpoint_file = save_checkpoint(
                user_events, batch_num, total_events, namespace_events
            )
            print(f"  💾 Checkpoint saved at batch {batch_num}")
            gc.collect()
        
        # Garbage collection
        if batch_num % 10 == 0:
            gc.collect()

    # Final checkpoint
    checkpoint_file = save_checkpoint(
        user_events, batch_num, total_events, namespace_events
    )
    
    print()
    print("=" * 70)
    print("DATA LOADING SUMMARY")
    print("=" * 70)
    print(f"Total events processed: {total_events:,}")
    print(f"Namespace events: {namespace_events:,} ({namespace_events/max(total_events,1)*100:.1f}%)")
    print(f"Users: {len(user_events):,}")
    print(f"Batches: {batch_num}")
    print("=" * 70)
    print()

    # Sort events by timestamp
    print("Sorting events by timestamp...")
    for user_id in user_events:
        user_events[user_id].sort(key=lambda e: e.timestamp)

    # Create traces
    print(f"Creating traces (min {MIN_EVENTS_PER_USER} events)...")
    traces = [
        InteractionTrace(events)
        for events in user_events.values()
        if len(events) >= MIN_EVENTS_PER_USER
    ]

    print(f"Created {len(traces):,} valid traces")
    print()

    return BenignDataset(traces)


def extract_features(dataset: BenignDataset) -> Dict:
    """Extract behavioral features from dataset."""
    print("=" * 70)
    print("EXTRACTING FEATURES")
    print("=" * 70)
    print()

    extractors = [
        TimingFeatureExtractor(),
        SessionFeatureExtractor(),
        TransitionFeatureExtractor(),
        FrequencyFeatureExtractor(),
        RevisitFeatureExtractor()
    ]

    feature_results = {}
    for extractor in extractors:
        print(f"  {extractor.name}...")
        try:
            feature_results[extractor.name] = extractor.extract(dataset)
            print(f"    ✓ Complete")
        except Exception as e:
            print(f"    ✗ Error: {e}")
            raise

    print()
    print("Computing statistics...")

    import numpy as np

    def compute_stats(values):
        if len(values) == 0:
            return {"count": 0}
        arr = np.array(values)
        return {
            "count": len(arr),
            "mean": float(np.mean(arr)),
            "median": float(np.median(arr)),
            "std": float(np.std(arr)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "percentiles": {
                "25": float(np.percentile(arr, 25)),
                "50": float(np.percentile(arr, 50)),
                "75": float(np.percentile(arr, 75)),
                "95": float(np.percentile(arr, 95)),
                "99": float(np.percentile(arr, 99))
            }
        }

    timing = feature_results["ft_intra_user_timing"]
    session = feature_results["fsession_length"]
    transition = feature_results["faccess_transition_matrix"][0]
    frequency = feature_results["f_event_type_frequency"][0]
    revisit = feature_results["f_artifact_revisit"]

    return {
        "metadata": {
            "description": "Empirical behavioral features from GitHub Archive",
            "data_source": "GitHub Archive June 1-7, 2025 (via Hugging Face)",
            "routing_namespace": list(ROUTING_NAMESPACE),
            "num_users": len(dataset),
            "extraction_date": datetime.now().isoformat(),
            "collaborator_indistinguishability": "Features aggregated across users",
            "max_events_per_user": MAX_EVENTS_PER_USER
        },
        "ft_intra_user_timing": {
            "statistics": compute_stats(timing),
            "sample_values": list(timing[:1000])
        },
        "fsession_length": {
            "statistics": compute_stats(session),
            "sample_values": list(session[:1000])
        },
        "faccess_transition_matrix": {
            "matrix": transition
        },
        "f_event_type_frequency": {
            "frequencies": frequency
        },
        "f_artifact_revisit": {
            "revisit_rate": {
                "statistics": compute_stats(revisit[0]),
                "sample_values": list(revisit[0][:1000])
            },
            "unique_artifacts": {
                "statistics": compute_stats(revisit[1]),
                "sample_values": list(revisit[1][:1000])
            },
            "max_revisits": {
                "statistics": compute_stats(revisit[2]),
                "sample_values": list(revisit[2][:1000])
            }
        }
    }


def main(resume: bool = True):
    """Main extraction workflow."""
    print()
    print("=" * 70)
    print("BEHAVIORAL FEATURE EXTRACTION (HF + CHECKPOINTS)")
    print("=" * 70)
    print()

    try:
        # Load data from Hugging Face (with checkpointing)
        dataset = load_gharchive_from_huggingface(resume=resume)
        
        # Extract features
        behavioral_priors = extract_features(dataset)

        # Save results
        output_file = Path(OUTPUT_JSON_PATH)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        print("Saving results...")
        with open(output_file, "w") as f:
            json.dump(behavioral_priors, f, indent=2)

        print()
        print("=" * 70)
        print("SUCCESS!")
        print("=" * 70)
        print(f"✓ Saved: {output_file}")
        print(f"  Users: {behavioral_priors['metadata']['num_users']:,}")
        print(f"  Timing deltas: {behavioral_priors['ft_intra_user_timing']['statistics']['count']:,}")
        print("=" * 70)
        print()
        
        # Clear checkpoint on success
        clear_checkpoint()
        
        print("✓ Complete!")
        print()

    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        print("Progress saved. Run again to resume from checkpoint.")
        print()
        raise
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("Progress saved. Run again to resume from checkpoint.")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main(resume=True)
