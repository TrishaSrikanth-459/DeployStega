#!/usr/bin/env python3
"""
Ablation experiments for DeployStega.

This script is intentionally a thin wrapper around adversarial_evaluation.py.
It runs multiple adversarial evaluation configurations and writes one summary
CSV for comparison.

Canonical logic lives in adversarial_evaluation.py:
- grouped train/validation/test splits
- feature extraction and vector schema
- validation-calibrated target-FPR threshold
- held-out test AUC / TPR / FPR / empirical epsilon
- behavioral, semantic, and cross-layer evaluation modes

Usage:
    python run_ablation.py --benign-dir /path/to/benign_datasets \
                           --covert-dir /path/to/covert_datasets \
                           [--manifest experiments/experiment_manifest.json] \
                           [--output-root ablation_results] \
                           [--target-fpr 0.05] \
                           [--test-size 0.3] \
                           [--validation-size 0.2] \
                           [--seed 42] \
                           [--include-bert]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Make both project imports and same-directory script imports work whether this
# file is launched from project root or from scripts/.
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from adversarial_evaluation import run_bert_evaluation, run_engineered_evaluation


# ----------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ablation experiments for DeployStega")
    parser.add_argument(
        "--benign-dir",
        required=True,
        help="Directory containing benign dataset files (JSONL)",
    )
    parser.add_argument(
        "--covert-dir",
        required=True,
        help="Directory containing covert dataset files (JSONL)",
    )
    parser.add_argument(
        "--manifest",
        default="experiments/experiment_manifest.json",
        help="Path to experiment manifest. Used only for epoch timing metadata.",
    )
    parser.add_argument(
        "--output-root",
        default="ablation_results",
        help="Root directory to save ablation results",
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
        "--user-key",
        type=str,
        default="role",
        help="How to group records into traces for behavioral features (supported: role, role_epoch)",
    )
    parser.add_argument(
        "--group-key",
        type=str,
        default="user_key",
        help="JSONL field used for grouped train/validation/test splitting",
    )
    parser.add_argument(
        "--epsilon-smoothing",
        type=float,
        default=1e-6,
        help="Smoothing used in log((TPR+s)/(FPR+s))",
    )
    parser.add_argument(
        "--include-bert",
        action="store_true",
        help="Also run BERT semantic detector ablations",
    )
    parser.add_argument(
        "--include-bert-context",
        action="store_true",
        help="When --include-bert is set, also run BERT with artifact/context text",
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
    return parser.parse_args()


# ----------------------------------------------------------------------
# Configs
# ----------------------------------------------------------------------
def build_ablation_configs(args: argparse.Namespace) -> List[Dict[str, Any]]:
    configs: List[Dict[str, Any]] = [
        {
            "name": "baseline_cross_rf",
            "features": "cross",
            "classifier": "rf",
            "bert_context": False,
        },
        {
            "name": "behavioral_only_rf",
            "features": "behavioral",
            "classifier": "rf",
            "bert_context": False,
        },
        {
            "name": "semantic_only_rf",
            "features": "semantic",
            "classifier": "rf",
            "bert_context": False,
        },
        {
            "name": "baseline_cross_lr",
            "features": "cross",
            "classifier": "logistic",
            "bert_context": False,
        },
        {
            "name": "baseline_cross_svm",
            "features": "cross",
            "classifier": "svm",
            "bert_context": False,
        },
    ]

    if args.include_bert:
        configs.append(
            {
                "name": "semantic_bert",
                "features": "semantic",
                "classifier": "bert",
                "bert_context": False,
            }
        )

        if args.include_bert_context:
            configs.append(
                {
                    "name": "semantic_bert_with_context",
                    "features": "semantic",
                    "classifier": "bert",
                    "bert_context": True,
                }
            )

    return configs


def make_eval_args(
    args: argparse.Namespace,
    cfg: Dict[str, Any],
    output_dir: Path,
) -> argparse.Namespace:
    return Namespace(
        features=cfg["features"],
        classifier=cfg["classifier"],
        bert_context=bool(cfg.get("bert_context", False)),
        benign_dir=args.benign_dir,
        covert_dir=args.covert_dir,
        target_fpr=args.target_fpr,
        test_size=args.test_size,
        validation_size=args.validation_size,
        seed=args.seed,
        output_dir=str(output_dir),
        manifest_path=args.manifest,
        workers=args.workers,
        no_progress=args.no_progress,
        max_samples=args.max_samples,
        bert_epochs=args.bert_epochs,
        bert_batch_size=args.bert_batch_size,
        bert_max_length=args.bert_max_length,
        user_key=args.user_key,
        group_key=args.group_key,
        epsilon_smoothing=args.epsilon_smoothing,
    )


# ----------------------------------------------------------------------
# Summary helpers
# ----------------------------------------------------------------------
def get_result_value(results: Dict[str, Any], key: str, default: Any = math.nan) -> Any:
    value = results.get(key, default)
    if value is None:
        return default
    return value


def make_success_row(cfg: Dict[str, Any], results: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": cfg["name"],
        "features": cfg["features"],
        "classifier": cfg["classifier"],
        "bert_context": bool(cfg.get("bert_context", False)),
        "epsilon": get_result_value(results, "epsilon"),
        "roc_auc": get_result_value(results, "roc_auc"),
        "target_fpr": get_result_value(results, "target_fpr"),
        "validation_threshold": get_result_value(results, "validation_threshold"),
        "validation_fpr": get_result_value(results, "validation_fpr"),
        "validation_tpr": get_result_value(results, "validation_tpr"),
        "actual_fpr": get_result_value(results, "actual_fpr"),
        "tpr": get_result_value(results, "tpr"),
        "tp": get_result_value(results, "tp"),
        "fp": get_result_value(results, "fp"),
        "tn": get_result_value(results, "tn"),
        "fn": get_result_value(results, "fn"),
        "feature_dim": get_result_value(results, "feature_dim", ""),
        "n_fit": get_result_value(results, "n_fit"),
        "n_validation": get_result_value(results, "n_validation"),
        "n_test": get_result_value(results, "n_test"),
        "error": "",
    }


def make_error_row(cfg: Dict[str, Any], err: Exception) -> Dict[str, Any]:
    return {
        "name": cfg["name"],
        "features": cfg["features"],
        "classifier": cfg["classifier"],
        "bert_context": bool(cfg.get("bert_context", False)),
        "epsilon": math.nan,
        "roc_auc": math.nan,
        "target_fpr": math.nan,
        "validation_threshold": math.nan,
        "validation_fpr": math.nan,
        "validation_tpr": math.nan,
        "actual_fpr": math.nan,
        "tpr": math.nan,
        "tp": math.nan,
        "fp": math.nan,
        "tn": math.nan,
        "fn": math.nan,
        "feature_dim": "",
        "n_fit": 0,
        "n_validation": 0,
        "n_test": 0,
        "error": str(err),
    }


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> None:
    args = parse_args()

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    with open(output_root / "ablation_args.json", "w", encoding="utf-8") as f:
        json.dump(vars(args), f, indent=2)

    configs = build_ablation_configs(args)

    summary: List[Dict[str, Any]] = []

    for cfg in configs:
        print("\n" + "=" * 72)
        print(f"Running ablation: {cfg['name']}")
        print(f"Features        : {cfg['features']}")
        print(f"Classifier      : {cfg['classifier']}")
        if cfg["classifier"] == "bert":
            print(f"BERT context    : {'enabled' if cfg.get('bert_context') else 'disabled'}")
        print("=" * 72)

        out_dir = output_root / cfg["name"]
        eval_args = make_eval_args(args, cfg, out_dir)

        try:
            if cfg["classifier"] == "bert":
                results = run_bert_evaluation(eval_args)
            else:
                results = run_engineered_evaluation(eval_args)

            summary.append(make_success_row(cfg, results))

        except Exception as err:
            print(f"Error in {cfg['name']}: {err}")
            out_dir.mkdir(parents=True, exist_ok=True)
            with open(out_dir / "error.json", "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "name": cfg["name"],
                        "features": cfg["features"],
                        "classifier": cfg["classifier"],
                        "bert_context": bool(cfg.get("bert_context", False)),
                        "error": str(err),
                    },
                    f,
                    indent=2,
                )
            summary.append(make_error_row(cfg, err))

    csv_path = output_root / "ablation_summary.csv"
    fieldnames = [
        "name",
        "features",
        "classifier",
        "bert_context",
        "epsilon",
        "roc_auc",
        "target_fpr",
        "validation_threshold",
        "validation_fpr",
        "validation_tpr",
        "actual_fpr",
        "tpr",
        "tp",
        "fp",
        "tn",
        "fn",
        "feature_dim",
        "n_fit",
        "n_validation",
        "n_test",
        "error",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary)

    with open(output_root / "ablation_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nAblation summary saved to {csv_path}")


if __name__ == "__main__":
    main()

