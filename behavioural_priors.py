"""
Extract behavioral priors from GitHub Archive data.
Parses GH Archive logs (June 1 - July 1, 2025) to extract empirical distributions of behavioral features.
"""
import json
import gzip
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict

# Import dataset classes first
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

__all__ = [
    'TimingFeatureExtractor',
    'SessionFeatureExtractor', 
    'TransitionFeatureExtractor',
    'FrequencyFeatureExtractor',
    'RevisitFeatureExtractor',
]

DATA_YEAR = 2025
DATA_MONTH_START = 6
DATA_DAY_START = 1
DATA_MONTH_END = 7
DATA_DAY_END = 1


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


def load_gharchive_data(data_dir: str = "data") -> BenignDataset:
  
    print("="*70)
    print("LOADING GITHUB ARCHIVE DATA")
    print("="*70)
    print(f"Date range: {DATA_YEAR}-{DATA_MONTH_START:02d}-{DATA_DAY_START:02d} to "
          f"{DATA_YEAR}-{DATA_MONTH_END:02d}-{DATA_DAY_END:02d}")
    print(f"Routing namespace: {len(ROUTING_NAMESPACE)} event types")
    print(f"Min events per user: {MIN_EVENTS_PER_USER}")
    print()

    data_path = Path(data_dir)
    files_to_process = []

    # Process June 1-July 1
    for day in range(DATA_DAY_START, 31):
        pattern = f"{DATA_YEAR}-{DATA_MONTH_START:02d}-{day:02d}-*.json.gz"
        files_to_process.extend(sorted(data_path.glob(pattern)))

    pattern = f"{DATA_YEAR}-{DATA_MONTH_END:02d}-{DATA_DAY_END:02d}-*.json.gz"
    files_to_process.extend(sorted(data_path.glob(pattern)))

    if not files_to_process:
        raise FileNotFoundError(f"No files found in {data_dir}/ for date range")

    print(f"Found {len(files_to_process)} files to process")
    print()

    user_events = defaultdict(list)
    total_events = 0
    namespace_events = 0

    for i, filepath in enumerate(files_to_process, 1):
        print(f"[{i}/{len(files_to_process)}] {filepath.name}...", end="", flush=True)

        file_events = 0

        with gzip.open(filepath, "rt") as f:
            for line in f:
                try:
                    event = json.loads(line)
                    event_type = event["type"]
                    total_events += 1

                    if event_type not in ROUTING_NAMESPACE:
                        continue

                    user_id = event["actor"]["id"]
                    timestamp_str = event["created_at"]
                    repo_id = event["repo"]["id"]

                    timestamp = datetime.fromisoformat(
                        timestamp_str.replace("Z", "+00:00")
                    ).timestamp()

                    artifact_class = _get_metadata_value(event, "artifact_class")

                    interaction_event = InteractionEvent(
                        timestamp=timestamp,
                        action_type=event_type,
                        artifact_ids=(repo_id,),
                        metadata=(("artifact_class", artifact_class),)
                    )

                    user_events[user_id].append(interaction_event)
                    file_events += 1
                    namespace_events += 1

                except (json.JSONDecodeError, KeyError):
                    continue

        print(f" {file_events:,} events")

    print()
    print(f"Total: {total_events:,} events")
    print(f"Namespace: {namespace_events:,} ({namespace_events/total_events*100:.1f}%)")
    print(f"Users: {len(user_events):,}")
    print()

    print("Sorting events")
    for user_id in user_events:
        user_events[user_id].sort(key=lambda e: e.timestamp)

    print(f"Creating traces (min {MIN_EVENTS_PER_USER} events)")
    traces = [
        InteractionTrace(events)
        for events in user_events.values()
        if len(events) >= MIN_EVENTS_PER_USER
    ]

    print(f"Created {len(traces):,} traces")
    print()

    return BenignDataset(traces)


def extract_features(dataset: BenignDataset) -> Dict:
    print("="*70)
    print("EXTRACTING FEATURES")
    print("="*70)
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
        feature_results[extractor.name] = extractor.extract(dataset)

    print()
    print("Computing statistics")

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
            "data_source": f"GitHub Archive {DATA_YEAR}-{DATA_MONTH_START:02d}-{DATA_DAY_START:02d} to "
                          f"{DATA_YEAR}-{DATA_MONTH_END:02d}-{DATA_DAY_END:02d}",
            "routing_namespace": list(ROUTING_NAMESPACE),
            "num_users": len(dataset),
            "extraction_date": datetime.now().isoformat(),
            "collaborator_indistinguishability": "Features aggregated across users"
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

def main():
    """Main extraction workflow."""
    print()
    print("="*70)
    print("BEHAVIORAL FEATURE EXTRACTION")
    print("="*70)
    print()

    try:
        # Load data
        dataset = load_gharchive_data("data")
        
        # Extract features
        behavioral_priors = extract_features(dataset)

        # Save results to behavioral_priors.json
        output_file = Path(OUTPUT_JSON_PATH)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w") as f:
            json.dump(behavioral_priors, f, indent=2)

        print("="*70)
        print(f"✓ Saved: {output_file}")
        print(f"  Users: {behavioral_priors['metadata']['num_users']:,}")
        print(f"  Timing deltas: {behavioral_priors['ft_intra_user_timing']['statistics']['count']:,}")
        print("="*70)
        print()
        print("✓ Complete! Run plot_behavioral_priors.py to visualize.")
        print()

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
