#!/usr/bin/env python3
"""
Adversarial evaluation pipeline for DeployStega using pre‑generated datasets.

This script:
- Loads many dataset files from two directories: benign/ and covert/.
- Extracts a feature vector for each dataset (using the same feature extractors).
- Trains a classifier to distinguish benign from covert datasets.
- Computes empirical ε = ln(TPR/FPR) at a target FPR and saves ROC curves.

Usage:
    python adversarial_evaluation.py --features {behavioral,semantic,cross} \\
                                     --classifier {logistic,rf,svm} \\
                                     --benign-dir path/to/benign_datasets/ \\
                                     --covert-dir path/to/covert_datasets/ \\
                                     [--target-fpr 0.05] [--test-size 0.3] \\
                                     [--seed 42] [--output-dir results] \\
                                     [--manifest-path experiments/experiment_manifest.json]
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
    parser = argparse.ArgumentParser(description="Adversarial evaluation for DeployStega using pre‑generated datasets")
    parser.add_argument("--features", choices=["behavioral", "semantic", "cross"],
                        required=True, help="Feature set to use")
    parser.add_argument("--classifier", choices=["logistic", "rf", "svm"],
                        required=True, help="Classifier type")
    parser.add_argument("--benign-dir", required=True,
                        help="Directory containing JSONL files of benign datasets")
    parser.add_argument("--covert-dir", required=True,
                        help="Directory containing JSONL files of covert datasets")
    parser.add_argument("--target-fpr", type=float, default=0.05,
                        help="Target false positive rate (default: 0.05)")
    parser.add_argument("--test-size", type=float, default=0.3,
                        help="Fraction of data to use for testing (default: 0.3)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility (default: 42)")
    parser.add_argument("--output-dir", type=str, default="results",
                        help="Directory to save results (default: results)")
    parser.add_argument("--manifest-path", type=str, default="experiments/experiment_manifest.json",
                        help="Path to experiment manifest JSON (optional)")
    return parser.parse_args()


# ----------------------------------------------------------------------
# Helper: get feature extractors based on selected feature set
# ----------------------------------------------------------------------
def get_extractors(feature_set):
    behavioral = [
        TimingFeatureExtractor(),
        SessionFeatureExtractor(),
        TransitionFeatureExtractor(),
        FrequencyFeatureExtractor(),
        RevisitFeatureExtractor(),
        IdentifierConcentrationFeatureExtractor(),
        RoleAsymmetryFeatureExtractor(),
        SharedAccessFeatureExtractor(),
        SharedAccessTopologyFeatureExtractor(),
    ]
    semantic = [SemanticFeatureExtractor()]
    if feature_set == "behavioral":
        return behavioral
    elif feature_set == "semantic":
        return semantic
    else:  # cross
        return behavioral + semantic


# ----------------------------------------------------------------------
# Helper: build feature vector from a dataset (single file)
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
# Main
# ----------------------------------------------------------------------
def main():
    args = parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "args.json", "w") as f:
        json.dump(vars(args), f, indent=2)

    print("\n=== DeployStega Adversarial Evaluation (Pre‑generated Datasets) ===")
    print(f"Feature set   : {args.features}")
    print(f"Classifier    : {args.classifier}")
    print(f"Benign dir    : {args.benign_dir}")
    print(f"Covert dir    : {args.covert_dir}")
    print(f"Target FPR    : {args.target_fpr}")
    print(f"Test size     : {args.test_size}")
    print(f"Seed          : {args.seed}")
    print(f"Output dir    : {out_dir}\n")

    # Optional timing policy
    timing_policy = None
    if args.manifest_path:
        try:
            ctx = load_experiment_context(args.manifest_path)
            timing_policy = TimingPolicy(
                epoch_origin_unix=ctx.epoch_origin_unix,
                epoch_duration_seconds=ctx.epoch_duration_seconds,
                spread_within_epoch_seconds=0.0
            )
        except Exception as e:
            print(f"Warning: could not load manifest, using None timing policy: {e}")

    # Set up feature extractors
    extractors = get_extractors(args.features)

    # Build template from one benign file (to ensure consistent vector dimensions)
    benign_dir = Path(args.benign_dir)
    benign_files = sorted(benign_dir.glob("*.jsonl"))
    if not benign_files:
        raise ValueError(f"No JSONL files found in {args.benign_dir}")
    print(f"Building template from first benign file: {benign_files[0].name}")
    template = build_template_from_file(benign_files[0], extractors, timing_policy)

    # Extract vectors for all benign files
    print(f"\nExtracting feature vectors from {len(benign_files)} benign datasets...")
    benign_vectors = []
    for fpath in benign_files:
        try:
            vec = extract_feature_vector_from_file(fpath, extractors, template, timing_policy)
            benign_vectors.append(vec)
        except Exception as e:
            print(f"Error processing {fpath}: {e}, skipping")
    benign_vectors = np.array(benign_vectors)
    print(f"  Extracted {len(benign_vectors)} benign vectors, dim={benign_vectors.shape[1]}")

    # Extract vectors for all covert files
    covert_dir = Path(args.covert_dir)
    covert_files = sorted(covert_dir.glob("*.jsonl"))
    if not covert_files:
        raise ValueError(f"No JSONL files found in {args.covert_dir}")
    print(f"Extracting feature vectors from {len(covert_files)} covert datasets...")
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
    y = np.array([0] * len(benign_vectors) + [1] * len(covert_vectors))

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=args.seed, stratify=y
    )

    print(f"\nTraining set size: {len(y_train)} (benign: {np.sum(y_train==0)}, covert: {np.sum(y_train==1)})")
    print(f"Test set size: {len(y_test)}")

    # Train classifier
    clf = get_classifier(args.classifier, args.seed)
    clf.fit(X_train, y_train)

    # Evaluate
    y_scores = clf.predict_proba(X_test)[:, 1]
    eps, fpr_target, tpr_target, fpr, tpr = compute_epsilon(y_test, y_scores, args.target_fpr)
    roc_auc = auc(fpr, tpr)

    print("\n=== Results ===")
    print(f"Target FPR       : {args.target_fpr}")
    print(f"Actual FPR       : {fpr_target:.4f}")
    print(f"TPR at that FPR  : {tpr_target:.4f}")
    print(f"Empirical ε      : {eps:.4f}")
    print(f"ROC AUC          : {roc_auc:.4f}")

    # Save results
    results = {
        "target_fpr": args.target_fpr,
        "actual_fpr": fpr_target,
        "tpr": tpr_target,
        "epsilon": eps,
        "roc_auc": roc_auc,
        "n_benign_datasets": len(benign_vectors),
        "n_covert_datasets": len(covert_vectors),
        "feature_dim": X.shape[1],
    }
    with open(out_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)

    joblib.dump(clf, out_dir / "classifier.pkl")
    np.savez(out_dir / "feature_vectors.npz", X=X, y=y)
    plot_roc(fpr, tpr, roc_auc,
             f"{args.features} features, {args.classifier} classifier",
             out_dir / "roc_curve.png")

    print(f"\nResults saved to {out_dir}")


if __name__ == "__main__":
    main()
