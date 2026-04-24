#!/usr/bin/env python3
"""
Adversarial evaluation pipeline for DeployStega.

This script evaluates whether adversarial classifiers can distinguish benign
routing traces from covert routing traces under three capability classes:

    behavioral : timing/session/frequency/routing/topology features
    semantic   : semantic engineered features from init-code/code.py,
                 or BERT when --classifier bert is used
    cross      : behavioral/routing + semantic engineered features

The reported empirical epsilon is computed as:

    epsilon = log((TPR + smoothing) / (FPR + smoothing))

The detection threshold is selected on a validation split at the target FPR,
then evaluated on a held-out test split. Splits are grouped by user/source key
to reduce leakage.
"""

from __future__ import annotations

import argparse
import csv
import functools
import importlib.util
import json
import math
import os
import sys
import warnings
from datetime import datetime, timezone
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import auc, roc_curve
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

try:
    from tqdm import tqdm

    HAS_TQDM = True
except Exception:
    tqdm = None
    HAS_TQDM = False

try:
    import torch
    from torch.utils.data import Dataset, DataLoader
    from transformers import BertTokenizer, BertForSequenceClassification

    HAS_BERT = True
except Exception:
    torch = None
    Dataset = object
    DataLoader = None
    BertTokenizer = None
    BertForSequenceClassification = None
    HAS_BERT = False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dataset.routing_trace_record import RoutingTraceRecord
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

from features.extractor import FeatureExtractor
from features.pipeline import FeatureExtractionPipeline
from scripts.experiment_context import load_experiment_context


NUMERIC_STAT_COUNT = 12


# ----------------------------------------------------------------------
# Load semantic module from init-code/code.py
# ----------------------------------------------------------------------
def load_semantic_module():
    semantic_path = PROJECT_ROOT / "init-code" / "code.py"
    if not semantic_path.exists():
        raise FileNotFoundError(
            f"Could not find semantic feature code at {semantic_path}"
        )

    spec = importlib.util.spec_from_file_location("deploystega_semantic_code", semantic_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module spec from {semantic_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SEMANTIC_MODULE = load_semantic_module()


# ----------------------------------------------------------------------
# Semantic extractor wrapper around init-code/code.py
# ----------------------------------------------------------------------
class SemanticFeatureExtractor(FeatureExtractor):
    """
    Adapter that computes semantic features from InteractionEvent.semantic_content
    using the functions in init-code/code.py.
    """

    __slots__ = ("_cfg",)

    def __init__(self):
        cfg = SEMANTIC_MODULE.Config()
        # Keep runtime somewhat sane for dataset-level extraction.
        cfg.pair_samples_per_type = min(getattr(cfg, "pair_samples_per_type", 100000), 2000)
        self._cfg = cfg

    @property
    def name(self) -> str:
        return "semantic"

    def _dataset_to_dataframe(self, dataset: BenignDataset) -> pd.DataFrame:
        rows: List[Dict[str, Any]] = []

        for trace_idx, trace in enumerate(dataset.traces()):
            for event_idx, event in enumerate(trace.events()):
                text = (event.semantic_content or "").replace("\x00", "").strip()
                if not text:
                    continue

                if len(text) > self._cfg.max_chars:
                    text = text[: self._cfg.max_chars]

                semantic_type = event.semantic_type or event.action_type or "unknown"
                rows.append(
                    {
                        "id": f"{trace_idx}:{event_idx}",
                        "type": str(semantic_type),
                        "text": text,
                    }
                )

        if not rows:
            return pd.DataFrame(columns=["id", "type", "text"])

        df = pd.DataFrame(rows).drop_duplicates(subset=["id"])
        df["type"] = df["type"].astype(str)
        return df

    def _zero_features(self) -> Dict[str, Any]:
        return {
            "num_texts": 0.0,
            "num_types": 0.0,
            "mean_chars": 0.0,
            "std_chars": 0.0,
            "ppl_mean": 0.0,
            "ppl_std": 0.0,
            "ppl_min": 0.0,
            "ppl_max": 0.0,
            "ntoks_mean": 0.0,
            "ntoks_std": 0.0,
            "kl_mean": 0.0,
            "kl_std": 0.0,
            "kl_min": 0.0,
            "kl_max": 0.0,
            "pair_count": 0.0,
            "pair_cos_mean": 0.0,
            "pair_cos_std": 0.0,
            "pair_cos_min": 0.0,
            "pair_cos_max": 0.0,
            "pair_by_type": {},
        }

    def extract(self, dataset: BenignDataset) -> Tuple[Any, ...]:
        df = self._dataset_to_dataframe(dataset)
        if df.empty:
            return (self._zero_features(),)

        char_lengths = df["text"].str.len().to_numpy(dtype=float)

        ppls, ntoks = SEMANTIC_MODULE.compute_ppl(df, self._cfg)
        kls = SEMANTIC_MODULE.compute_kl(df, self._cfg)
        embs = SEMANTIC_MODULE.compute_embeddings(df, self._cfg)
        pair_df = SEMANTIC_MODULE.sample_pair_distances(df, embs, self._cfg)

        features: Dict[str, Any] = {
            "num_texts": float(len(df)),
            "num_types": float(df["type"].nunique()),
            "mean_chars": float(np.mean(char_lengths)) if len(char_lengths) else 0.0,
            "std_chars": float(np.std(char_lengths)) if len(char_lengths) else 0.0,
            "ppl_mean": float(np.mean(ppls)) if len(ppls) else 0.0,
            "ppl_std": float(np.std(ppls)) if len(ppls) else 0.0,
            "ppl_min": float(np.min(ppls)) if len(ppls) else 0.0,
            "ppl_max": float(np.max(ppls)) if len(ppls) else 0.0,
            "ntoks_mean": float(np.mean(ntoks)) if len(ntoks) else 0.0,
            "ntoks_std": float(np.std(ntoks)) if len(ntoks) else 0.0,
            "kl_mean": float(np.mean(kls)) if len(kls) else 0.0,
            "kl_std": float(np.std(kls)) if len(kls) else 0.0,
            "kl_min": float(np.min(kls)) if len(kls) else 0.0,
            "kl_max": float(np.max(kls)) if len(kls) else 0.0,
            "pair_count": float(len(pair_df)),
            "pair_cos_mean": 0.0,
            "pair_cos_std": 0.0,
            "pair_cos_min": 0.0,
            "pair_cos_max": 0.0,
            "pair_by_type": {},
        }

        if len(pair_df) > 0:
            cos = pair_df["cos_dist"].to_numpy(dtype=float)
            features["pair_cos_mean"] = float(np.mean(cos))
            features["pair_cos_std"] = float(np.std(cos))
            features["pair_cos_min"] = float(np.min(cos))
            features["pair_cos_max"] = float(np.max(cos))

            by_type: Dict[str, Dict[str, float]] = {}
            for t, sub in pair_df.groupby("type"):
                vals = sub["cos_dist"].to_numpy(dtype=float)
                by_type[str(t)] = {
                    "count": float(len(vals)),
                    "mean": float(np.mean(vals)) if len(vals) else 0.0,
                    "std": float(np.std(vals)) if len(vals) else 0.0,
                }
            features["pair_by_type"] = by_type

        return (features,)


@dataclass(frozen=True)
class FileEntry:
    path: Path
    label: int
    group: str


@dataclass(frozen=True)
class TextSample:
    text: str
    context: str
    label: int
    group: str
    source_file: str


# ----------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Adversarial evaluation for DeployStega")
    parser.add_argument(
        "--features",
        choices=["behavioral", "semantic", "cross"],
        required=True,
        help="Adversarial capability class to evaluate",
    )
    parser.add_argument(
        "--classifier",
        choices=["logistic", "rf", "svm", "bert"],
        required=True,
        help="Classifier type. Use bert only with --features semantic.",
    )
    parser.add_argument(
        "--bert-context",
        action="store_true",
        help="Use artifact/context text with BERT",
    )
    parser.add_argument(
        "--benign-dir",
        required=True,
        help="Directory containing benign JSONL datasets",
    )
    parser.add_argument(
        "--covert-dir",
        required=True,
        help="Directory containing covert JSONL datasets",
    )
    parser.add_argument(
        "--target-fpr",
        type=float,
        default=0.05,
        help="Target validation false-positive rate",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.3,
        help="Fraction of grouped files reserved for held-out test",
    )
    parser.add_argument(
        "--validation-size",
        type=float,
        default=0.2,
        help="Fraction of train files reserved for threshold calibration",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results",
        help="Directory to save results",
    )
    parser.add_argument(
        "--manifest-path",
        type=str,
        default="experiments/experiment_manifest.json",
        help="Path to experiment manifest JSON",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, os.cpu_count() or 1),
        help="Parallel workers for engineered feature extraction",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bars",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=10000,
        help="Maximum text samples for BERT evaluation",
    )
    parser.add_argument(
        "--bert-epochs",
        type=int,
        default=3,
        help="BERT training epochs",
    )
    parser.add_argument(
        "--bert-batch-size",
        type=int,
        default=16,
        help="BERT training batch size",
    )
    parser.add_argument(
        "--bert-max-length",
        type=int,
        default=128,
        help="Maximum BERT token length",
    )
    parser.add_argument(
        "--user-key",
        type=str,
        default="role",
        help="How to group records into traces for behavioral features (supported: role, role_epoch)",
    )
    parser.add_argument(
        "--group-key",
        type=str,
        default="user_key",
        help="JSONL field used for grouped splitting",
    )
    parser.add_argument(
        "--epsilon-smoothing",
        type=float,
        default=1e-6,
        help="Smoothing for finite epsilon estimates",
    )
    return parser.parse_args()


# ----------------------------------------------------------------------
# File and split helpers
# ----------------------------------------------------------------------
def read_first_json_object(filepath: Path) -> Dict[str, Any]:
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                return json.loads(line)
    return {}


def file_has_routing_events(filepath: Path) -> bool:
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            if "epoch" in obj and ("identifier" in obj or "url" in obj):
                return True
    return False


def get_group_key_from_file(filepath: Path, group_key: str) -> str:
    first = read_first_json_object(filepath)
    for key in (group_key, "experiment_id", "user_key", "source_user_key", "source_trace_id", "trace_id", "repo"):
        value = first.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return filepath.stem


def build_file_entries(benign_dir: str, covert_dir: str, group_key: str) -> List[FileEntry]:
    benign_files = sorted(Path(benign_dir).glob("*.jsonl"))
    covert_files = sorted(Path(covert_dir).glob("*.jsonl"))

    if not benign_files:
        raise ValueError(f"No benign JSONL files found in {benign_dir}")
    if not covert_files:
        raise ValueError(f"No covert JSONL files found in {covert_dir}")

    filtered_benign_files = [path for path in benign_files if file_has_routing_events(path)]
    filtered_covert_files = [path for path in covert_files if file_has_routing_events(path)]

    skipped_benign = len(benign_files) - len(filtered_benign_files)
    skipped_covert = len(covert_files) - len(filtered_covert_files)
    if skipped_benign:
        print(f"Skipping {skipped_benign} benign files with no event rows")
    if skipped_covert:
        print(f"Skipping {skipped_covert} covert files with no event rows")

    if not filtered_benign_files:
        raise ValueError(f"No usable benign JSONL files found in {benign_dir}")
    if not filtered_covert_files:
        raise ValueError(f"No usable covert JSONL files found in {covert_dir}")

    entries: List[FileEntry] = []
    for path in filtered_benign_files:
        entries.append(FileEntry(path=path, label=0, group=get_group_key_from_file(path, group_key)))
    for path in filtered_covert_files:
        entries.append(FileEntry(path=path, label=1, group=get_group_key_from_file(path, group_key)))

    return entries


def split_entries_by_group(
    entries: Sequence[FileEntry],
    test_size: float,
    seed: int,
    split_name: str,
) -> Tuple[List[FileEntry], List[FileEntry]]:
    groups: Dict[str, List[FileEntry]] = defaultdict(list)
    for entry in entries:
        groups[entry.group].append(entry)

    group_items = list(groups.items())
    if len(group_items) < 2:
        raise ValueError(f"{split_name}: need at least 2 groups for grouped split")

    rng = np.random.default_rng(seed)
    target_test_groups = max(1, int(round(len(group_items) * test_size)))

    best_split: Optional[Tuple[List[FileEntry], List[FileEntry]]] = None
    best_score = float("inf")

    for _ in range(200):
        shuffled = group_items[:]
        rng.shuffle(shuffled)

        test_group_names = {name for name, _ in shuffled[:target_test_groups]}
        train_entries: List[FileEntry] = []
        test_entries: List[FileEntry] = []

        for name, group_entries in shuffled:
            if name in test_group_names:
                test_entries.extend(group_entries)
            else:
                train_entries.extend(group_entries)

        train_labels = {e.label for e in train_entries}
        test_labels = {e.label for e in test_entries}

        if train_labels == {0, 1} and test_labels == {0, 1}:
            return sorted(train_entries, key=lambda e: str(e.path)), sorted(test_entries, key=lambda e: str(e.path))

        score = abs(len(test_entries) - round(len(entries) * test_size))
        score += 1000 if train_labels != {0, 1} else 0
        score += 1000 if test_labels != {0, 1} else 0
        if score < best_score:
            best_score = score
            best_split = (train_entries, test_entries)

    if best_split is None:
        raise ValueError(f"{split_name}: could not construct grouped split")

    train_entries, test_entries = best_split
    raise ValueError(
        f"{split_name}: grouped split could not preserve both classes in train and test. "
        f"train_labels={sorted({e.label for e in train_entries})}, "
        f"test_labels={sorted({e.label for e in test_entries})}. "
        "Use more files/groups or a different --group-key."
    )


def labels_from_entries(entries: Sequence[FileEntry]) -> np.ndarray:
    return np.array([e.label for e in entries], dtype=int)


# ----------------------------------------------------------------------
# Engineered feature extraction
# ----------------------------------------------------------------------
def get_extractors(feature_set: str) -> list:
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
    if feature_set == "semantic":
        return semantic
    if feature_set == "cross":
        return behavioral + semantic

    raise ValueError(f"Unknown feature set: {feature_set}")


def parse_timestamp_value(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return float(raw)
        except Exception:
            pass

        iso_value = raw.replace(" UTC", "+00:00")
        if iso_value.endswith("Z"):
            iso_value = iso_value[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(iso_value).timestamp()
        except Exception:
            pass

        for fmt in ("%Y-%m-%d %H:%M:%S UTC", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                dt = datetime.strptime(raw, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except Exception:
                continue
    return None


def normalize_routing_record(obj: Dict[str, Any], filepath: Path, lineno: int) -> Optional[RoutingTraceRecord]:
    if not isinstance(obj, dict):
        raise TypeError(f"JSONL line {lineno} in {filepath} must be an object")

    # Benign traces can start with lightweight metadata/header rows like {"repo": [...]}.
    if "epoch" not in obj and "identifier" not in obj and "url" not in obj:
        return None

    role = str(obj.get("role") or "user").strip().lower()
    if role not in {"sender", "receiver", "user"}:
        role = "user"

    epoch_raw = obj.get("epoch")
    if epoch_raw is None:
        raise ValueError(f"Missing epoch on line {lineno} in {filepath}")
    try:
        epoch = int(epoch_raw)
    except Exception as exc:
        raise ValueError(f"Invalid epoch on line {lineno} in {filepath}: {epoch_raw}") from exc
    if epoch < 0:
        raise ValueError(f"Invalid epoch on line {lineno} in {filepath}: {epoch_raw}")

    artifact_class = obj.get("artifact_class") or obj.get("artifactClass") or "Repository"
    artifact_class = str(artifact_class).strip() or "Repository"

    identifier_raw = obj.get("identifier", obj.get("repo"))
    if isinstance(identifier_raw, tuple):
        identifier = identifier_raw
    elif isinstance(identifier_raw, list):
        identifier = tuple(identifier_raw)
    elif identifier_raw is not None:
        identifier = (identifier_raw,)
    else:
        raise ValueError(f"Missing identifier on line {lineno} in {filepath}")

    url = obj.get("url")
    if url is None:
        raise ValueError(f"Missing url on line {lineno} in {filepath}")
    url = str(url).strip()
    if not url:
        raise ValueError(f"Empty url on line {lineno} in {filepath}")

    metadata_raw = obj.get("metadata", ())
    if metadata_raw is None:
        metadata = ()
    elif isinstance(metadata_raw, tuple):
        metadata = metadata_raw
    elif isinstance(metadata_raw, list):
        metadata = tuple(metadata_raw)
    else:
        metadata = (metadata_raw,)

    return RoutingTraceRecord(
        role=role,
        epoch=epoch,
        artifact_class=artifact_class,
        identifier=identifier,
        url=url,
        experiment_id=str(obj["experiment_id"]) if obj.get("experiment_id") is not None else None,
        timestamp=parse_timestamp_value(obj.get("timestamp")),
        action_type=str(obj.get("action_type") or obj.get("actionType") or obj.get("action") or "route_access").strip() or "route_access",
        metadata=metadata,
        semantic_text=obj.get("semantic_text"),
        semantic_meaning=obj.get("semantic_meaning"),
        semantic_ref=obj.get("semantic_ref"),
        semantic_label=obj.get("semantic_label"),
        semantic_content_type=obj.get("semantic_content_type"),
    )


def load_normalized_routing_records(filepath: Path) -> Tuple[RoutingTraceRecord, ...]:
    records: List[RoutingTraceRecord] = []
    with open(filepath, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception as exc:
                raise ValueError(f"Invalid JSON on line {lineno} in {filepath}") from exc
            record = normalize_routing_record(obj, filepath, lineno)
            if record is not None:
                records.append(record)

    if not records:
        raise ValueError(f"No routing trace records found in {filepath}")
    return tuple(records)


def load_feature_set_from_file(
    filepath: Path,
    extractors: Sequence[Any],
    timing_policy: Optional[TimingPolicy],
    user_key: str,
):
    records = load_normalized_routing_records(filepath)

    effective_user_key = user_key if user_key in {"role", "role_epoch"} else "role"
    traces_by_user = build_interaction_traces(
        records=records,
        user_key=effective_user_key,
        timing_policy=timing_policy,
    )
    traces = list(traces_by_user.values())
    if not traces:
        raise ValueError(f"No traces found in {filepath}")

    dataset = BenignDataset(traces)
    pipeline = FeatureExtractionPipeline(extractors)
    return pipeline.run(dataset)

def process_feature_entries(
    entries: Sequence[FileEntry],
    extractors: Sequence[Any],
    timing_policy: Optional[TimingPolicy],
    user_key: str,
    workers: int,
    use_progress: bool,
    desc: str,
) -> Tuple[List[FileEntry], List[Any], List[str]]:
    worker_func = functools.partial(
        load_feature_set_from_file,
        extractors=extractors,
        timing_policy=timing_policy,
        user_key=user_key,
    )

    ok_entries: List[FileEntry] = []
    feature_sets: List[Any] = []
    errors: List[str] = []

    if workers <= 1:
        iterator = entries
        if use_progress and HAS_TQDM:
            iterator = tqdm(entries, desc=desc)
        for entry in iterator:
            try:
                feature_sets.append(worker_func(entry.path))
                ok_entries.append(entry)
            except Exception as e:
                msg = f"Error processing {entry.path}: {e}"
                print(msg)
                errors.append(msg)
        return ok_entries, feature_sets, errors

    import concurrent.futures

    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        future_to_entry = {executor.submit(worker_func, entry.path): entry for entry in entries}
        futures = list(future_to_entry.keys())

        iterator = concurrent.futures.as_completed(futures)
        if use_progress and HAS_TQDM:
            iterator = tqdm(iterator, total=len(futures), desc=desc)

        for future in iterator:
            entry = future_to_entry[future]
            try:
                feature_sets.append(future.result())
                ok_entries.append(entry)
            except Exception as e:
                msg = f"Error processing {entry.path}: {e}"
                print(msg)
                errors.append(msg)

    return ok_entries, feature_sets, errors


def safe_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
        if math.isnan(parsed) or math.isinf(parsed):
            return None
        return parsed
    except Exception:
        return None


def numeric_stats(values: Iterable[Any]) -> List[float]:
    cleaned = [safe_float(v) for v in values]
    arr = np.array([v for v in cleaned if v is not None], dtype=float)

    if arr.size == 0:
        return [0.0] * NUMERIC_STAT_COUNT

    return [
        float(arr.size),
        float(np.mean(arr)),
        float(np.std(arr)),
        float(np.min(arr)),
        float(np.max(arr)),
        float(np.percentile(arr, 1)),
        float(np.percentile(arr, 5)),
        float(np.percentile(arr, 25)),
        float(np.percentile(arr, 50)),
        float(np.percentile(arr, 75)),
        float(np.percentile(arr, 95)),
        float(np.percentile(arr, 99)),
    ]


def flatten_dict_keys(d: Dict[str, Any], prefix: Tuple[str, ...] = ()) -> List[Tuple[str, ...]]:
    keys: List[Tuple[str, ...]] = []
    for key in sorted(d.keys()):
        value = d[key]
        next_prefix = prefix + (str(key),)
        if isinstance(value, dict):
            keys.extend(flatten_dict_keys(value, next_prefix))
        else:
            keys.append(next_prefix)
    return keys


def get_nested_value(d: Dict[str, Any], path: Tuple[str, ...]) -> Any:
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return 0.0
        cur = cur[key]
    return cur


def infer_feature_type(vals: Sequence[Any]) -> Optional[str]:
    if not vals:
        return None
    first = vals[0]
    if isinstance(first, (int, float, np.integer, np.floating)):
        return "numeric"
    if isinstance(first, tuple):
        return "tuple"
    if isinstance(first, dict):
        return "dict"
    return None


def update_schema(schema: Dict[str, Dict[str, Any]], feature_set: Any) -> None:
    for name in sorted(feature_set.names()):
        vals = feature_set.get(name)
        if not vals:
            continue

        kind = infer_feature_type(vals)
        if kind is None:
            warnings.warn(f"Skipping unsupported feature {name} of type {type(vals[0])}")
            continue

        if name not in schema:
            schema[name] = {"kind": kind}

        if schema[name]["kind"] != kind:
            warnings.warn(
                f"Feature {name} changed type from {schema[name]['kind']} to {kind}; keeping first type."
            )
            continue

        if kind == "tuple":
            current_len = int(schema[name].get("tuple_len", 0))
            observed_len = max((len(v) for v in vals if isinstance(v, tuple)), default=0)
            schema[name]["tuple_len"] = max(current_len, observed_len)

        elif kind == "dict":
            keys = set(tuple(k) for k in schema[name].get("keys", []))
            for item in vals:
                if isinstance(item, dict):
                    keys.update(flatten_dict_keys(item))
            schema[name]["keys"] = sorted(keys)


def build_schema(feature_sets: Sequence[Any]) -> Dict[str, Dict[str, Any]]:
    schema: Dict[str, Dict[str, Any]] = {}
    for feature_set in feature_sets:
        update_schema(schema, feature_set)
    if not schema:
        raise ValueError("No usable features extracted")
    return schema


def feature_set_to_vector(feature_set: Any, schema: Dict[str, Dict[str, Any]]) -> np.ndarray:
    feature_names = set(feature_set.names())
    vector_parts: List[float] = []

    for name in sorted(schema.keys()):
        spec = schema[name]
        vals = feature_set.get(name) if name in feature_names else []
        kind = spec["kind"]

        if kind == "numeric":
            vector_parts.extend(numeric_stats(vals))

        elif kind == "tuple":
            tuple_len = int(spec.get("tuple_len", 0))
            for i in range(tuple_len):
                component_values = []
                for v in vals:
                    if isinstance(v, tuple) and len(v) > i:
                        component_values.append(v[i])
                vector_parts.extend(numeric_stats(component_values))

        elif kind == "dict":
            keys = [tuple(k) for k in spec.get("keys", [])]
            for key_path in keys:
                key_values = []
                for item in vals:
                    if isinstance(item, dict):
                        key_values.append(get_nested_value(item, key_path))
                parsed = [safe_float(v) for v in key_values]
                parsed = [v for v in parsed if v is not None]
                vector_parts.append(float(np.mean(parsed)) if parsed else 0.0)

        else:
            raise ValueError(f"Unsupported schema kind: {kind}")

    arr = np.array(vector_parts, dtype=float)
    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)


def vectorize_feature_sets(feature_sets: Sequence[Any], schema: Dict[str, Dict[str, Any]]) -> np.ndarray:
    vectors = [feature_set_to_vector(fs, schema) for fs in feature_sets]
    if not vectors:
        raise ValueError("No feature vectors produced")
    return np.vstack(vectors)


# ----------------------------------------------------------------------
# Classifiers and metrics
# ----------------------------------------------------------------------
def get_classifier(name: str, random_state: int):
    if name == "logistic":
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=5000, random_state=random_state, class_weight="balanced"),
        )
    if name == "rf":
        return RandomForestClassifier(
            n_estimators=300,
            random_state=random_state,
            class_weight="balanced",
            n_jobs=-1,
        )
    if name == "svm":
        return make_pipeline(
            StandardScaler(),
            SVC(probability=True, random_state=random_state, class_weight="balanced"),
        )
    raise ValueError(f"Unknown classifier: {name}")


def choose_threshold_at_target_fpr(
    y_true: np.ndarray,
    y_scores: np.ndarray,
    target_fpr: float,
) -> Tuple[float, float, float]:
    fpr, tpr, thresholds = roc_curve(y_true, y_scores)

    candidates = np.where(fpr <= target_fpr)[0]
    if len(candidates) == 0:
        idx = int(np.argmin(np.abs(fpr - target_fpr)))
    else:
        idx = int(candidates[np.argmax(tpr[candidates])])

    return float(thresholds[idx]), float(fpr[idx]), float(tpr[idx])


def evaluate_threshold(
    y_true: np.ndarray,
    y_scores: np.ndarray,
    threshold: float,
    smoothing: float,
) -> Dict[str, float]:
    pred = (y_scores >= threshold).astype(int)

    positives = y_true == 1
    negatives = y_true == 0

    tp = int(np.sum((pred == 1) & positives))
    fn = int(np.sum((pred == 0) & positives))
    fp = int(np.sum((pred == 1) & negatives))
    tn = int(np.sum((pred == 0) & negatives))

    tpr = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    epsilon = math.log((tpr + smoothing) / (fpr + smoothing))

    return {
        "actual_fpr": float(fpr),
        "tpr": float(tpr),
        "epsilon": float(epsilon),
        "tp": float(tp),
        "fp": float(fp),
        "tn": float(tn),
        "fn": float(fn),
    }


def plot_roc(fpr: np.ndarray, tpr: np.ndarray, auc_val: float, title: str, save_path: Path) -> None:
    plt.figure()
    plt.plot(fpr, tpr, color="darkorange", lw=2, label=f"ROC curve (AUC = {auc_val:.2f})")
    plt.plot([0, 1], [0, 1], color="navy", lw=2, linestyle="--")
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title(title)
    plt.legend(loc="lower right")
    plt.grid(True)
    plt.savefig(save_path)
    plt.close()


def write_scores_csv(
    path: Path,
    entries_or_samples: Sequence[Any],
    y_true: Sequence[int],
    scores: Sequence[float],
) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["source_file", "group", "label", "score"])
        writer.writeheader()
        for item, label, score in zip(entries_or_samples, y_true, scores):
            if isinstance(item, FileEntry):
                source_file = str(item.path)
                group = item.group
            else:
                source_file = item.source_file
                group = item.group
            writer.writerow(
                {
                    "source_file": source_file,
                    "group": group,
                    "label": int(label),
                    "score": float(score),
                }
            )


# ----------------------------------------------------------------------
# BERT semantic evaluation
# ----------------------------------------------------------------------
class StegoBERTDataset(Dataset):
    def __init__(
        self,
        samples: Sequence[TextSample],
        use_context: bool,
        max_length: int,
    ):
        self.tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")
        self.samples = list(samples)
        self.use_context = use_context
        self.max_length = max_length

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx: int):
        sample = self.samples[idx]
        text = sample.text
        if self.use_context and sample.context:
            text = f"{sample.context} [SEP] {sample.text}"

        encoding = self.tokenizer(
            text,
            truncation=True,
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt",
        )

        return {
            "input_ids": encoding["input_ids"].flatten(),
            "attention_mask": encoding["attention_mask"].flatten(),
            "label": torch.tensor(sample.label, dtype=torch.long),
        }


class BERTSemanticClassifier:
    def __init__(
        self,
        use_context: bool,
        max_length: int,
        device: Optional[str] = None,
    ):
        if not HAS_BERT:
            raise RuntimeError("BERT dependencies are unavailable. Install torch and transformers.")

        self.use_context = use_context
        self.max_length = max_length
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = BertForSequenceClassification.from_pretrained("bert-base-uncased", num_labels=2)
        self.model.to(self.device)

    def train(
        self,
        train_samples: Sequence[TextSample],
        val_samples: Sequence[TextSample],
        epochs: int,
        batch_size: int,
        lr: float = 2e-5,
    ) -> None:
        train_dataset = StegoBERTDataset(train_samples, self.use_context, self.max_length)
        val_dataset = StegoBERTDataset(val_samples, self.use_context, self.max_length)

        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size)

        optimizer = torch.optim.AdamW(self.model.parameters(), lr=lr)

        for epoch in range(epochs):
            self.model.train()
            total_loss = 0.0

            iterator = train_loader
            if HAS_TQDM:
                iterator = tqdm(train_loader, desc=f"BERT epoch {epoch + 1}/{epochs}")

            for batch in iterator:
                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)
                labels = batch["label"].to(self.device)

                optimizer.zero_grad()
                outputs = self.model(input_ids, attention_mask=attention_mask, labels=labels)
                loss = outputs.loss
                loss.backward()
                optimizer.step()

                total_loss += float(loss.item())

            val_acc = self.accuracy(val_samples, batch_size=batch_size)
            mean_loss = total_loss / max(1, len(train_loader))
            print(f"Epoch {epoch + 1}: loss={mean_loss:.4f}, val_acc={val_acc:.4f}")

    def accuracy(self, samples: Sequence[TextSample], batch_size: int) -> float:
        dataset = StegoBERTDataset(samples, self.use_context, self.max_length)
        loader = DataLoader(dataset, batch_size=batch_size)

        self.model.eval()
        correct = 0
        total = 0

        with torch.no_grad():
            for batch in loader:
                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)
                labels = batch["label"].to(self.device)

                outputs = self.model(input_ids, attention_mask=attention_mask)
                predictions = torch.argmax(outputs.logits, dim=-1)
                correct += int((predictions == labels).sum().item())
                total += int(len(labels))

        return correct / total if total else 0.0

    def predict_proba(self, samples: Sequence[TextSample], batch_size: int) -> np.ndarray:
        dataset = StegoBERTDataset(samples, self.use_context, self.max_length)
        loader = DataLoader(dataset, batch_size=batch_size)

        self.model.eval()
        all_probs: List[float] = []

        with torch.no_grad():
            for batch in loader:
                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)

                outputs = self.model(input_ids, attention_mask=attention_mask)
                probs = torch.softmax(outputs.logits, dim=-1)
                all_probs.extend([float(x) for x in probs[:, 1].cpu().numpy()])

        return np.array(all_probs, dtype=float)

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self.model.save_pretrained(path)
        tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")
        tokenizer.save_pretrained(path)


def text_from_event(event: Dict[str, Any]) -> str:
    for key in ("semantic_text", "text", "body", "message", "content", "title"):
        value = event.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def context_from_event(event: Dict[str, Any]) -> str:
    parts: List[str] = []

    artifact_class = event.get("artifact_class")
    if artifact_class:
        parts.append(f"Artifact: {artifact_class}")

    action = event.get("action") or event.get("event_type") or event.get("type")
    if action:
        parts.append(f"Action: {action}")

    parent = event.get("parent_text")
    if parent and len(str(parent)) > 10:
        parts.append(f"Parent: {str(parent)[:200]}")

    repo = event.get("repo") or event.get("repository")
    if repo:
        parts.append(f"Repo: {repo}")

    repo_files = event.get("repo_files")
    if isinstance(repo_files, list):
        paths = []
        for item in repo_files[:5]:
            if isinstance(item, dict) and item.get("path"):
                paths.append(str(item["path"]))
            elif isinstance(item, str):
                paths.append(item)
        if paths:
            parts.append(f"Files: {', '.join(paths)}")

    return " | ".join(parts)


def extract_text_samples_from_file(entry: FileEntry) -> List[TextSample]:
    samples: List[TextSample] = []

    with open(entry.path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            obj = json.loads(line)

            if isinstance(obj.get("events"), list):
                events = obj["events"]
            else:
                events = [obj]

            for event in events:
                if not isinstance(event, dict):
                    continue
                text = text_from_event(event)
                if not text:
                    continue
                samples.append(
                    TextSample(
                        text=text,
                        context=context_from_event(event),
                        label=entry.label,
                        group=entry.group,
                        source_file=str(entry.path),
                    )
                )

    return samples


def collect_text_samples(entries: Sequence[FileEntry]) -> List[TextSample]:
    samples: List[TextSample] = []
    for entry in entries:
        samples.extend(extract_text_samples_from_file(entry))
    return samples


def balanced_limit_samples(
    samples: Sequence[TextSample],
    max_samples: Optional[int],
    seed: int,
) -> List[TextSample]:
    if not max_samples or len(samples) <= max_samples:
        return list(samples)

    rng = np.random.default_rng(seed)
    by_label: Dict[int, List[TextSample]] = defaultdict(list)
    for sample in samples:
        by_label[sample.label].append(sample)

    labels = sorted(by_label.keys())
    per_label = max(1, max_samples // max(1, len(labels)))

    selected: List[TextSample] = []
    for label in labels:
        label_samples = by_label[label]
        indices = np.arange(len(label_samples))
        rng.shuffle(indices)
        selected.extend([label_samples[i] for i in indices[:per_label]])

    rng.shuffle(selected)
    return selected[:max_samples]


def labels_from_samples(samples: Sequence[TextSample]) -> np.ndarray:
    return np.array([s.label for s in samples], dtype=int)


# ----------------------------------------------------------------------
# Evaluation modes
# ----------------------------------------------------------------------
def run_engineered_evaluation(args: argparse.Namespace) -> Dict[str, Any]:
    entries = build_file_entries(args.benign_dir, args.covert_dir, args.group_key)
    trainval_entries, test_entries = split_entries_by_group(
        entries, args.test_size, args.seed, "train/test"
    )
    fit_entries, val_entries = split_entries_by_group(
        trainval_entries, args.validation_size, args.seed + 17, "fit/validation"
    )

    print(f"Fit files : {len(fit_entries)}")
    print(f"Val files : {len(val_entries)}")
    print(f"Test files: {len(test_entries)}")

    timing_policy = None
    if args.manifest_path:
        try:
            ctx = load_experiment_context(args.manifest_path)
            timing_policy = TimingPolicy(
                epoch_origin_unix=ctx.epoch_origin_unix,
                epoch_duration_seconds=ctx.epoch_duration_seconds,
                spread_within_epoch_seconds=0.0,
            )
        except Exception as e:
            print(f"Warning: could not load manifest, using no timing policy: {e}")

    extractors = get_extractors(args.features)
    use_progress = not args.no_progress
    effective_workers = args.workers
    if args.features in {"semantic", "cross"} and effective_workers != 1:
        print("Semantic features rely on dynamically loaded code; forcing --workers=1 to avoid multiprocessing pickling failures.")
        effective_workers = 1

    fit_ok, fit_sets, fit_errors = process_feature_entries(
        fit_entries, extractors, timing_policy, args.user_key, effective_workers, use_progress, "Fit features"
    )
    val_ok, val_sets, val_errors = process_feature_entries(
        val_entries, extractors, timing_policy, args.user_key, effective_workers, use_progress, "Val features"
    )
    test_ok, test_sets, test_errors = process_feature_entries(
        test_entries, extractors, timing_policy, args.user_key, effective_workers, use_progress, "Test features"
    )

    if not fit_sets or not val_sets or not test_sets:
        raise ValueError("Feature extraction produced an empty fit/val/test split")

    y_fit = labels_from_entries(fit_ok)
    y_val = labels_from_entries(val_ok)
    y_test = labels_from_entries(test_ok)

    if len(set(y_fit)) < 2 or len(set(y_val)) < 2 or len(set(y_test)) < 2:
        raise ValueError("Fit, validation, and test splits must each contain both classes")

    schema = build_schema(fit_sets + val_sets)

    X_fit = vectorize_feature_sets(fit_sets, schema)
    X_val = vectorize_feature_sets(val_sets, schema)
    X_test = vectorize_feature_sets(test_sets, schema)

    print(f"Feature dim: {X_fit.shape[1]}")
    print(f"Fit labels : benign={np.sum(y_fit == 0)}, covert={np.sum(y_fit == 1)}")
    print(f"Val labels : benign={np.sum(y_val == 0)}, covert={np.sum(y_val == 1)}")
    print(f"Test labels: benign={np.sum(y_test == 0)}, covert={np.sum(y_test == 1)}")

    clf = get_classifier(args.classifier, args.seed)
    clf.fit(X_fit, y_fit)

    val_scores = clf.predict_proba(X_val)[:, 1]
    threshold, val_fpr, val_tpr = choose_threshold_at_target_fpr(
        y_val, val_scores, args.target_fpr
    )

    test_scores = clf.predict_proba(X_test)[:, 1]
    fpr, tpr, _ = roc_curve(y_test, test_scores)
    roc_auc = float(auc(fpr, tpr))
    threshold_metrics = evaluate_threshold(
        y_test, test_scores, threshold, args.epsilon_smoothing
    )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "mode": "engineered",
        "features": args.features,
        "classifier": args.classifier,
        "target_fpr": args.target_fpr,
        "validation_threshold": threshold,
        "validation_fpr": val_fpr,
        "validation_tpr": val_tpr,
        "actual_fpr": threshold_metrics["actual_fpr"],
        "tpr": threshold_metrics["tpr"],
        "epsilon": threshold_metrics["epsilon"],
        "roc_auc": roc_auc,
        "tp": threshold_metrics["tp"],
        "fp": threshold_metrics["fp"],
        "tn": threshold_metrics["tn"],
        "fn": threshold_metrics["fn"],
        "feature_dim": int(X_fit.shape[1]),
        "n_fit": int(len(y_fit)),
        "n_validation": int(len(y_val)),
        "n_test": int(len(y_test)),
        "user_key": args.user_key,
        "group_key": args.group_key,
        "epsilon_smoothing": args.epsilon_smoothing,
        "fit_errors": fit_errors,
        "validation_errors": val_errors,
        "test_errors": test_errors,
    }

    with open(out_dir / "results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    split_manifest = {
        "fit_files": [str(e.path) for e in fit_ok],
        "validation_files": [str(e.path) for e in val_ok],
        "test_files": [str(e.path) for e in test_ok],
    }
    with open(out_dir / "split_manifest.json", "w", encoding="utf-8") as f:
        json.dump(split_manifest, f, indent=2)

    with open(out_dir / "feature_schema.json", "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)

    joblib.dump(clf, out_dir / "classifier.pkl")
    np.savez(
        out_dir / "feature_vectors.npz",
        X_fit=X_fit,
        y_fit=y_fit,
        X_val=X_val,
        y_val=y_val,
        X_test=X_test,
        y_test=y_test,
        val_scores=val_scores,
        test_scores=test_scores,
        threshold=np.array([threshold]),
    )
    write_scores_csv(out_dir / "validation_scores.csv", val_ok, y_val, val_scores)
    write_scores_csv(out_dir / "test_scores.csv", test_ok, y_test, test_scores)

    plot_roc(
        fpr,
        tpr,
        roc_auc,
        f"{args.features} features, {args.classifier}",
        out_dir / "roc_curve.png",
    )

    return results


def run_bert_evaluation(args: argparse.Namespace) -> Dict[str, Any]:
    if not HAS_BERT:
        raise RuntimeError("BERT dependencies are unavailable. Install torch and transformers.")

    if args.features != "semantic":
        raise ValueError("--classifier bert is only supported with --features semantic")

    entries = build_file_entries(args.benign_dir, args.covert_dir, args.group_key)
    trainval_entries, test_entries = split_entries_by_group(
        entries, args.test_size, args.seed, "train/test"
    )
    fit_entries, val_entries = split_entries_by_group(
        trainval_entries, args.validation_size, args.seed + 17, "fit/validation"
    )

    fit_samples = collect_text_samples(fit_entries)
    val_samples = collect_text_samples(val_entries)
    test_samples = collect_text_samples(test_entries)

    fit_samples = balanced_limit_samples(fit_samples, args.max_samples, args.seed)
    val_samples = balanced_limit_samples(val_samples, max(100, args.max_samples // 5), args.seed + 1)
    test_samples = balanced_limit_samples(test_samples, max(100, args.max_samples // 5), args.seed + 2)

    if not fit_samples or not val_samples or not test_samples:
        raise ValueError("BERT text extraction produced an empty fit/val/test split")

    y_fit = labels_from_samples(fit_samples)
    y_val = labels_from_samples(val_samples)
    y_test = labels_from_samples(test_samples)

    if len(set(y_fit)) < 2 or len(set(y_val)) < 2 or len(set(y_test)) < 2:
        raise ValueError("BERT fit, validation, and test splits must each contain both classes")

    print(f"Fit text samples : {len(fit_samples)}")
    print(f"Val text samples : {len(val_samples)}")
    print(f"Test text samples: {len(test_samples)}")
    print(f"BERT context     : {'enabled' if args.bert_context else 'disabled'}")

    clf = BERTSemanticClassifier(
        use_context=args.bert_context,
        max_length=args.bert_max_length,
    )
    clf.train(
        fit_samples,
        val_samples,
        epochs=args.bert_epochs,
        batch_size=args.bert_batch_size,
    )

    val_scores = clf.predict_proba(val_samples, batch_size=args.bert_batch_size)
    threshold, val_fpr, val_tpr = choose_threshold_at_target_fpr(
        y_val, val_scores, args.target_fpr
    )

    test_scores = clf.predict_proba(test_samples, batch_size=args.bert_batch_size)
    fpr, tpr, _ = roc_curve(y_test, test_scores)
    roc_auc = float(auc(fpr, tpr))
    threshold_metrics = evaluate_threshold(
        y_test, test_scores, threshold, args.epsilon_smoothing
    )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "mode": "bert",
        "features": args.features,
        "classifier": args.classifier,
        "bert_context": bool(args.bert_context),
        "target_fpr": args.target_fpr,
        "validation_threshold": threshold,
        "validation_fpr": val_fpr,
        "validation_tpr": val_tpr,
        "actual_fpr": threshold_metrics["actual_fpr"],
        "tpr": threshold_metrics["tpr"],
        "epsilon": threshold_metrics["epsilon"],
        "roc_auc": roc_auc,
        "tp": threshold_metrics["tp"],
        "fp": threshold_metrics["fp"],
        "tn": threshold_metrics["tn"],
        "fn": threshold_metrics["fn"],
        "n_fit": int(len(y_fit)),
        "n_validation": int(len(y_val)),
        "n_test": int(len(y_test)),
        "group_key": args.group_key,
        "epsilon_smoothing": args.epsilon_smoothing,
    }

    with open(out_dir / "results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    split_manifest = {
        "fit_files": sorted({s.source_file for s in fit_samples}),
        "validation_files": sorted({s.source_file for s in val_samples}),
        "test_files": sorted({s.source_file for s in test_samples}),
    }
    with open(out_dir / "split_manifest.json", "w", encoding="utf-8") as f:
        json.dump(split_manifest, f, indent=2)

    clf.save(out_dir / "bert_model")
    np.savez(
        out_dir / "bert_scores.npz",
        y_val=y_val,
        val_scores=val_scores,
        y_test=y_test,
        test_scores=test_scores,
        threshold=np.array([threshold]),
    )
    write_scores_csv(out_dir / "validation_scores.csv", val_samples, y_val, val_scores)
    write_scores_csv(out_dir / "test_scores.csv", test_samples, y_test, test_scores)

    plot_roc(
        fpr,
        tpr,
        roc_auc,
        f"BERT semantic {'with context' if args.bert_context else 'without context'}",
        out_dir / "roc_curve.png",
    )

    return results


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> None:
    args = parse_args()

    if args.classifier == "bert" and args.features != "semantic":
        raise ValueError("Use --classifier bert only with --features semantic")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "args.json", "w", encoding="utf-8") as f:
        json.dump(vars(args), f, indent=2)

    print("\n=== DeployStega Adversarial Evaluation ===")
    print(f"Features      : {args.features}")
    print(f"Classifier    : {args.classifier}")
    print(f"Benign dir    : {args.benign_dir}")
    print(f"Covert dir    : {args.covert_dir}")
    print(f"Target FPR    : {args.target_fpr}")
    print(f"Test size     : {args.test_size}")
    print(f"Validation    : {args.validation_size}")
    print(f"Seed          : {args.seed}")
    print(f"User key      : {args.user_key}")
    print(f"Group key     : {args.group_key}")
    print(f"Output dir    : {out_dir}\n")

    if args.classifier == "bert":
        results = run_bert_evaluation(args)
    else:
        results = run_engineered_evaluation(args)

    print("\n=== Results ===")
    print(f"Validation FPR       : {results['validation_fpr']:.4f}")
    print(f"Validation TPR       : {results['validation_tpr']:.4f}")
    print(f"Test actual FPR      : {results['actual_fpr']:.4f}")
    print(f"Test TPR             : {results['tpr']:.4f}")
    print(f"Empirical epsilon    : {results['epsilon']:.4f}")
    print(f"ROC AUC              : {results['roc_auc']:.4f}")
    print(f"\nResults saved to {out_dir}")


if __name__ == "__main__":
    main()

