#!/usr/bin/env python3
"""
Ablation experiments for DeployStega.

This script runs multiple evaluations with different feature sets and
ablation settings (e.g., removing certain extractors, disabling jitter,
etc.). It produces a summary CSV for easy comparison.

Usage:
    python run_ablation.py --benign-dir /path/to/benign_datasets \\
                           --covert-dir /path/to/covert_datasets \\
                           [--manifest experiments/experiment_manifest.json] \\
                           [--output-root ablation_results] \\
                           [--target-fpr 0.05] [--test-size 0.3] [--seed 42]
"""

import numpy as np
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_curve, auc
import sys
import joblib
import argparse
import json
import csv
import matplotlib.pyplot as plt

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dataset.trace_builder import TraceBuilder
from dataset.routing_trace_record import read_routing_trace_jsonl
from dataset.routing_trace_to_interaction import TimingPolicy, build_interaction_traces
from dataset.benign_dataset import BenignDataset

from features.behaviourial.timing import TimingFeatureExtractor
from features.behaviourial.session import SessionFeatureExtractor
from features.behaviourial.transition import TransitionFeatureExtractor
from features.behaviourial.frequency import FrequencyFeatureExtractor
from features.behaviourial.revisit import RevisitFeatureExtractor

from features.routing.identifier_concentration import IdentifierConcentrationFeatureExtractor
from features.routing.role_asymmetry import RoleAsymmetryFeatureExtractor
from features.routing.shared_access import SharedAccessFeatureExtractor
from features.routing.shared_access_topology import SharedAccessTopologyFeatureExtractor

from features.semantic.semantic import SemanticFeatureExtractor
from features.extraction_pipeline import FeatureExtractionPipeline
from features.feature_set import FeatureSet
from scripts.experiment_context import load_experiment_context


# ----------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="Ablation experiments for DeployStega")
    parser.add_argument("--benign-dir", required=True,
                        help="Directory containing benign dataset files (JSONL)")
    parser.add_argument("--covert-dir", required=True,
                        help="Directory containing covert dataset files (JSONL)")
    parser.add_argument("--manifest", default="experiments/experiment_manifest.json",
                        help="Path to experiment manifest (optional)")
    parser.add_argument("--output-root", default="ablation_results",
                        help="Root directory to save ablation results (default: ablation_results)")
    parser.add_argument("--target-fpr", type=float, default=0.05,
                        help="Target false positive rate (default: 0.05)")
    parser.add_argument("--test-size", type=float, default=0.3,
                        help="Fraction of data to use for testing (default: 0.3)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed (default: 42)")
    return parser.parse_args()


# ----------------------------------------------------------------------
# Helper: get feature extractors by name list
# ----------------------------------------------------------------------
EXTRACTOR_REGISTRY = {
    "timing": TimingFeatureExtractor,
    "session": SessionFeatureExtractor,
    "transition": TransitionFeatureExtractor,
    "frequency": FrequencyFeatureExtractor,
    "revisit": RevisitFeatureExtractor,
    "id_conc": IdentifierConcentrationFeatureExtractor,
    "role_asym": RoleAsymmetryFeatureExtractor,
    "shared": SharedAccessFeatureExtractor,
    "shared_topo": SharedAccessTopologyFeatureExtractor,
    "semantic": SemanticFeatureExtractor,
}

def get_extractors_by_names(names):
    """Return list of extractor instances for the given names."""
    extractors = []
    for name in names:
        if name not in EXTRACTOR_REGISTRY:
            raise ValueError(f"Unknown extractor: {name}")
        extractors.append(EXTRACTOR_REGISTRY[name]())
    return extractors


# ----------------------------------------------------------------------
# Helper: build feature vector from a single dataset file
# ----------------------------------------------------------------------
def extract_feature_vector_from_file(filepath, extractors, template=None, timing_policy=None):
    """
    Load a JSONL file (RoutingTraceRecord format), convert to a BenignDataset,
    and extract a feature vector.
    """
    records = read_routing_trace_jsonl(str(filepath))
    traces_by_user = build_interaction_traces(
        records=records,
        user_key="role",
        timing_policy=timing_policy
    )
    # Convert to BenignDataset (list of traces)
    traces = list(traces_by_user.values())
    if not traces:
        raise ValueError(f"No traces found in {filepath}")
    dataset = BenignDataset(traces)

    # Extract feature vector
    pipeline = FeatureExtractionPipeline(extractors)
    feature_set = pipeline.run(dataset)

    vector_parts = []
    for name in sorted(feature_set.names()):
        vals = feature_set.get(name)
        if len(vals) == 0:
            continue

        first = vals[0]

        if isinstance(first, (int, float)):
            arr = np.array(vals)
            if len(arr) == 0:
                stats = [0.0] * 13
            else:
                stats = [
                    len(arr),
                    np.mean(arr),
                    np.std(arr),
                    np.min(arr),
                    np.max(arr),
                    np.percentile(arr, 1),
                    np.percentile(arr, 5),
                    np.percentile(arr, 25),
                    np.percentile(arr, 50),
                    np.percentile(arr, 75),
                    np.percentile(arr, 95),
                    np.percentile(arr, 99)
                ]
            vector_parts.extend([float(x) for x in stats])

        elif isinstance(first, tuple):
            for inner in vals:
                arr = np.array(inner)
                if len(arr) == 0:
                    stats = [0.0] * 13
                else:
                    stats = [
                        len(arr),
                        np.mean(arr),
                        np.std(arr),
                        np.min(arr),
                        np.max(arr),
                        np.percentile(arr, 1),
                        np.percentile(arr, 5),
                        np.percentile(arr, 25),
                        np.percentile(arr, 50),
                        np.percentile(arr, 75),
                        np.percentile(arr, 95),
                        np.percentile(arr, 99)
                    ]
                vector_parts.extend([float(x) for x in stats])

        elif isinstance(first, dict):
            d = vals[0]
            if template and name in template:
                key_order = template[name]
                if key_order and isinstance(key_order[0], tuple):
                    for outer, inner in key_order:
                        if outer in d and isinstance(d[outer], dict) and inner in d[outer]:
                            vector_parts.append(float(d[outer][inner]))
                        else:
                            vector_parts.append(0.0)
                else:
                    for k in key_order:
                        vector_parts.append(float(d.get(k, 0.0)))
            else:
                if any(isinstance(v, dict) for v in d.values()):
                    for k1 in sorted(d.keys()):
                        inner = d[k1]
                        if isinstance(inner, dict):
                            for k2 in sorted(inner.keys()):
                                vector_parts.append(float(inner[k2]))
                        else:
                            vector_parts.append(float(inner))
                else:
                    for k in sorted(d.keys()):
                        vector_parts.append(float(d[k]))

        else:
            print(f"Warning: unhandled type {type(first)} for feature {name} in {filepath}")
            continue

    return np.array(vector_parts)


def build_template_from_file(filepath, extractors, timing_policy=None):
    """Build a template from a single file (e.g., first benign file)."""
    records = read_routing_trace_jsonl(str(filepath))
    traces_by_user = build_interaction_traces(
        records=records,
        user_key="role",
        timing_policy=timing_policy
    )
    traces = list(traces_by_user.values())
    if not traces:
        raise ValueError(f"No traces found in template file {filepath}")
    dataset = BenignDataset(traces)

    pipeline = FeatureExtractionPipeline(extractors)
    feature_set = pipeline.run(dataset)
    template = {}
    for name in sorted(feature_set.names()):
        vals = feature_set.get(name)
        if len(vals) == 0:
            continue
        first = vals[0]
        if isinstance(first, dict):
            d = vals[0]
            if any(isinstance(v, dict) for v in d.values()):
                key_order = []
                for k1 in sorted(d.keys()):
                    inner = d[k1]
                    if isinstance(inner, dict):
                        for k2 in sorted(inner.keys()):
                            key_order.append((k1, k2))
                    else:
                        key_order.append(k1)
                template[name] = key_order
            else:
                template[name] = sorted(d.keys())
    return template


def get_classifier(name, random_state):
    if name == "logistic":
        return LogisticRegression(max_iter=1000, random_state=random_state)
    elif name == "rf":
        return RandomForestClassifier(n_estimators=100, random_state=random_state)
    elif name == "svm":
        return SVC(probability=True, random_state=random_state)
    else:
        raise ValueError(f"Unknown classifier: {name}")


def compute_epsilon(y_true, y_scores, target_fpr):
    fpr, tpr, thresholds = roc_curve(y_true, y_scores)
    idx = np.argmin(np.abs(fpr - target_fpr))
    tpr_target = tpr[idx]
    fpr_target = fpr[idx]
    if fpr_target == 0:
        eps = np.inf
    else:
        eps = np.log(tpr_target / fpr_target)
    return eps, fpr_target, tpr_target, fpr, tpr


def plot_roc(fpr, tpr, auc_val, title, save_path):
    plt.figure()
    plt.plot(fpr, tpr, color='darkorange', lw=2, label=f'ROC curve (AUC = {auc_val:.2f})')
    plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--')
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title(title)
    plt.legend(loc="lower right")
    plt.grid(True)
    plt.savefig(save_path)
    plt.close()


# ----------------------------------------------------------------------
# Main evaluation function (can be called with a config dict)
# ----------------------------------------------------------------------
def run_evaluation(
    benign_dir,
    covert_dir,
    extractor_names,           # list of extractor names to use
    classifier_name,
    target_fpr=0.05,
    test_size=0.3,
    seed=42,
    output_dir=None,
    manifest_path=None,
    # Additional ablation knobs (to be used later)
    enable_timing_jitter=True,
):
    """
    Run a single evaluation with the given configuration.
    Returns epsilon, AUC, and a results dict.
    """
    # Build extractors
    extractors = get_extractors_by_names(extractor_names)

    # Timing policy (if needed)
    timing_policy = None
    if manifest_path:
        try:
            ctx = load_experiment_context(manifest_path)
            spread = 0.0 if not enable_timing_jitter else 0.0  # you can define a non‑zero spread if desired
            timing_policy = TimingPolicy(
                epoch_origin_unix=ctx.epoch_origin_unix,
                epoch_duration_seconds=ctx.epoch_duration_seconds,
                spread_within_epoch_seconds=spread
            )
        except Exception as e:
            print(f"Warning: could not load manifest, using None timing policy: {e}")

    # Get list of benign and covert files
    benign_files = sorted(Path(benign_dir).glob("*.jsonl"))
    covert_files = sorted(Path(covert_dir).glob("*.jsonl"))
    if not benign_files or not covert_files:
        raise ValueError("Benign or covert directory contains no JSONL files")

    # Build template from first benign file
    print(f"Building template from {benign_files[0].name}")
    template = build_template_from_file(benign_files[0], extractors, timing_policy)

    # Extract vectors for benign files
    print("Extracting benign vectors...")
    benign_vectors = []
    for fpath in benign_files:
        try:
            vec = extract_feature_vector_from_file(fpath, extractors, template, timing_policy)
            benign_vectors.append(vec)
        except Exception as e:
            print(f"Error processing {fpath}: {e}, skipping")
    benign_vectors = np.array(benign_vectors)
    print(f"  Extracted {len(benign_vectors)} benign vectors, dim={benign_vectors.shape[1]}")

    # Extract vectors for covert files
    print("Extracting covert vectors...")
    covert_vectors = []
    for fpath in covert_files:
        try:
            vec = extract_feature_vector_from_file(fpath, extractors, template, timing_policy)
            covert_vectors.append(vec)
        except Exception as e:
            print(f"Error processing {fpath}: {e}, skipping")
    covert_vectors = np.array(covert_vectors)
    print(f"  Extracted {len(covert_vectors)} covert vectors, dim={covert_vectors.shape[1]}")

    # Combine
    X = np.vstack([benign_vectors, covert_vectors])
    y = np.array([0]*len(benign_vectors) + [1]*len(covert_vectors))

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=y
    )
    print(f"Training set size: {len(y_train)} (benign: {np.sum(y_train==0)}, covert: {np.sum(y_train==1)})")
    print(f"Test set size: {len(y_test)}")

    # Train classifier
    clf = get_classifier(classifier_name, seed)
    clf.fit(X_train, y_train)

    # Evaluate
    y_scores = clf.predict_proba(X_test)[:, 1]
    eps, fpr_target, tpr_target, fpr, tpr = compute_epsilon(y_test, y_scores, target_fpr)
    roc_auc = auc(fpr, tpr)

    # Save if output_dir provided
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        results = {
            "target_fpr": target_fpr,
            "actual_fpr": fpr_target,
            "tpr": tpr_target,
            "epsilon": eps,
            "roc_auc": roc_auc,
            "n_benign": len(benign_vectors),
            "n_covert": len(covert_vectors),
            "feature_dim": X.shape[1],
            "extractor_names": extractor_names,
            "classifier": classifier_name,
        }
        with open(output_dir / "results.json", "w") as f:
            json.dump(results, f, indent=2)
        joblib.dump(clf, output_dir / "classifier.pkl")
        np.savez(output_dir / "feature_vectors.npz", X=X, y=y)
        plot_roc(fpr, tpr, roc_auc,
                 f"{', '.join(extractor_names)} | {classifier_name}",
                 output_dir / "roc.png")
        print(f"Saved results to {output_dir}")

    return eps, roc_auc, results


# ----------------------------------------------------------------------
# Main ablation loop
# ----------------------------------------------------------------------
def main():
    args = parse_args()

    # Define ablation configurations
    # Each config is a dict with keys: name, extractor_names, classifier_name, enable_timing_jitter
    # You can expand this list.
    configs = [
        {
            "name": "baseline_cross_rf",
            "extractor_names": ["timing", "session", "transition", "frequency", "revisit",
                                "id_conc", "role_asym", "shared", "shared_topo", "semantic"],
            "classifier_name": "rf",
        },
        {
            "name": "behavioral_only_rf",
            "extractor_names": ["timing", "session", "transition", "frequency", "revisit",
                                "id_conc", "role_asym", "shared", "shared_topo"],
            "classifier_name": "rf",
        },
        {
            "name": "semantic_only_rf",
            "extractor_names": ["semantic"],
            "classifier_name": "rf",
        },
        {
            "name": "baseline_cross_lr",
            "extractor_names": ["timing", "session", "transition", "frequency", "revisit",
                                "id_conc", "role_asym", "shared", "shared_topo", "semantic"],
            "classifier_name": "logistic",
        },
        {
            "name": "baseline_cross_svm",
            "extractor_names": ["timing", "session", "transition", "frequency", "revisit",
                                "id_conc", "role_asym", "shared", "shared_topo", "semantic"],
            "classifier_name": "svm",
        },
        # You can add more: remove routing features only, remove timing, etc.
    ]

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    summary = []
    for cfg in configs:
        print("\n" + "="*60)
        print(f"Running configuration: {cfg['name']}")
        print("="*60)
        out_dir = output_root / cfg["name"]
        try:
            eps, auc_val, res = run_evaluation(
                benign_dir=args.benign_dir,
                covert_dir=args.covert_dir,
                extractor_names=cfg["extractor_names"],
                classifier_name=cfg["classifier_name"],
                target_fpr=args.target_fpr,
                test_size=args.test_size,
                seed=args.seed,
                output_dir=out_dir,
                manifest_path=args.manifest,
                enable_timing_jitter=True,   # can add more knobs later
            )
            summary.append({
                "name": cfg["name"],
                "epsilon": eps,
                "roc_auc": auc_val,
                "n_benign": res["n_benign"],
                "n_covert": res["n_covert"],
                "error": ""
            })
        except Exception as e:
            print(f"Error in {cfg['name']}: {e}")
            summary.append({
                "name": cfg["name"],
                "epsilon": float('nan'),
                "roc_auc": float('nan'),
                "n_benign": 0,
                "n_covert": 0,
                "error": str(e)
            })

    # Write summary CSV
    csv_path = output_root / "ablation_summary.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "epsilon", "roc_auc", "n_benign", "n_covert", "error"])
        writer.writeheader()
        writer.writerows(summary)

    print(f"\nAblation summary saved to {csv_path}")


if __name__ == "__main__":
    main()
