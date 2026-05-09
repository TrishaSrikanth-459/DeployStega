#!/usr/bin/env python3
"""Colab orchestration for DeployStega full trace generation and evaluation.

This runner assumes the repository code has been cloned and the experiment data
(benign_traces/, secrets/, behavior_priors.json, and experiments/experiment_manifest.json)
are present in the working tree. It intentionally reads Azure credentials from
environment variables rather than storing secrets in the repository.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

REQUIRED_ENV = (
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_VERSION",
)


def run(cmd: List[str], *, cwd: Path, log_path: Path | None = None) -> None:
    print("\n$ " + " ".join(cmd), flush=True)
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log:
            proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            assert proc.stdout is not None
            for line in proc.stdout:
                print(line, end="")
                log.write(line)
                log.flush()
            rc = proc.wait()
        if rc != 0:
            raise subprocess.CalledProcessError(rc, cmd)
    else:
        subprocess.run(cmd, cwd=str(cwd), check=True)


def count_files(path: Path, pattern: str = "*.jsonl") -> int:
    return sum(1 for _ in path.glob(pattern)) if path.exists() else 0


def assert_inputs(root: Path) -> None:
    missing: List[str] = []
    if count_files(root / "benign_traces", "*.jsonl") == 0:
        missing.append("benign_traces/*.jsonl")
    if count_files(root / "secrets", "*.txt") == 0:
        missing.append("secrets/*.txt")
    for rel in ("behavior_priors.json", "experiments/experiment_manifest.json"):
        if not (root / rel).exists():
            missing.append(rel)
    if missing:
        raise SystemExit(
            "Missing experiment inputs: " + ", ".join(missing) + "\n"
            "Upload/extract the original data before running the full Colab experiment."
        )


def assert_env() -> None:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if not (os.environ.get("AZURE_OPENAI_DEPLOYMENT") or os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")):
        missing.append("AZURE_OPENAI_DEPLOYMENT or AZURE_OPENAI_DEPLOYMENT_NAME")
    if missing:
        raise SystemExit("Missing Azure OpenAI environment variables: " + ", ".join(missing))
    if not os.environ.get("AZURE_OPENAI_DEPLOYMENT") and os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME"):
        os.environ["AZURE_OPENAI_DEPLOYMENT"] = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]


def read_jsonl_texts(trace_dir: Path, limit: int = 2500) -> List[str]:
    texts: List[str] = []
    keys = ("semantic_text", "text", "body", "message", "content", "title")
    for path in sorted(trace_dir.glob("*.jsonl")):
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                for key in keys:
                    value = obj.get(key)
                    if value is not None and str(value).strip():
                        texts.append(str(value).strip())
                        break
                if len(texts) >= limit:
                    return texts
    return texts


def comparable_pr_issue_edit_texts(trace_dir: Path, limit: int = 2500) -> List[str]:
    """Collect normalized PullRequest/Issue edit text for source-leak smoke tests.

    This mirrors the diagnostic that caught the previous semantic source gap:
    compare only event types both sides actually share, after applying the same
    symmetric source-format normalization used by adversarial_evaluation.py.
    """
    from scripts.adversarial_evaluation import normalize_semantic_text_for_detection

    texts: List[str] = []
    keys = ("semantic_text", "text", "body", "message", "content", "title")
    for path in sorted(trace_dir.glob("*.jsonl")):
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue

                artifact_class = str(obj.get("artifact_class") or obj.get("artifactClass") or "")
                if artifact_class not in {"PullRequest", "Issue"}:
                    continue

                raw_text = ""
                for key in keys:
                    value = obj.get(key)
                    if value is not None and str(value).strip():
                        raw_text = str(value)
                        break
                text = normalize_semantic_text_for_detection(raw_text)
                if not text or len(text.split()) < 4:
                    continue

                action_raw = obj.get("action") or obj.get("action_type") or obj.get("actionType") or obj.get("event_type")
                action = str(action_raw).strip().lower() if action_raw else "edit"
                if action != "edit":
                    continue

                texts.append(text)
                if len(texts) >= limit:
                    return texts
    return texts


def tfidf_source_diagnostic(
    benign_dir: Path,
    covert_sender_dir: Path,
    report_path: Path,
    *,
    max_samples_per_class: int = 2500,
    seed: int = 42,
    repeats: int = 5,
) -> Dict[str, Any]:
    """Run a lightweight semantic source-leak smoke test.

    A near-perfect TF-IDF classifier here means the run is probably measuring
    generator/source style rather than subtle steganographic semantics.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, roc_auc_score
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import make_pipeline

    benign_texts = comparable_pr_issue_edit_texts(benign_dir, limit=max_samples_per_class)
    covert_texts = comparable_pr_issue_edit_texts(covert_sender_dir, limit=max_samples_per_class)

    rng = __import__("random").Random(seed)
    rng.shuffle(benign_texts)
    rng.shuffle(covert_texts)
    n = min(len(benign_texts), len(covert_texts), max_samples_per_class)

    report: Dict[str, Any] = {
        "mode": "tfidf_source_diagnostic",
        "support": "PullRequest/Issue edit text only",
        "normalization": "normalize_semantic_text_for_detection",
        "benign_count": len(benign_texts),
        "covert_count": len(covert_texts),
        "balanced_n_per_class": n,
        "auc_mean": None,
        "accuracy_mean": None,
        "runs": [],
        "benign_examples": benign_texts[:5],
        "covert_examples": covert_texts[:5],
    }

    if n < 20:
        report["skipped"] = True
        report["reason"] = "Need at least 20 comparable texts per class for a stable smoke diagnostic."
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2)[:4000])
        return report

    texts = benign_texts[:n] + covert_texts[:n]
    labels = [0] * n + [1] * n

    for rep in range(repeats):
        x_train, x_test, y_train, y_test = train_test_split(
            texts,
            labels,
            test_size=0.35,
            random_state=seed + rep,
            stratify=labels,
        )
        clf = make_pipeline(
            TfidfVectorizer(
                lowercase=True,
                strip_accents="unicode",
                ngram_range=(1, 2),
                min_df=2 if n >= 80 else 1,
                max_features=20000,
            ),
            LogisticRegression(max_iter=2000, class_weight="balanced"),
        )
        clf.fit(x_train, y_train)
        scores = clf.predict_proba(x_test)[:, 1]
        preds = (scores >= 0.5).astype(int)
        report["runs"].append(
            {
                "repeat": rep,
                "auc": float(roc_auc_score(y_test, scores)),
                "accuracy": float(accuracy_score(y_test, preds)),
            }
        )

    report["auc_mean"] = float(sum(r["auc"] for r in report["runs"]) / len(report["runs"]))
    report["accuracy_mean"] = float(sum(r["accuracy"] for r in report["runs"]) / len(report["runs"]))
    report["skipped"] = False

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2)[:4000])
    return report


def enforce_semantic_source_gate(
    report: Dict[str, Any],
    *,
    max_auc: float,
    max_accuracy: float,
    label: str,
) -> None:
    if report.get("skipped"):
        print(f"{label}: semantic source diagnostic skipped: {report.get('reason')}")
        return
    auc = report.get("auc_mean")
    acc = report.get("accuracy_mean")
    if auc is None or acc is None:
        return
    if float(auc) >= max_auc and float(acc) >= max_accuracy:
        raise SystemExit(
            f"{label}: semantic source diagnostic failed "
            f"(AUC={auc:.4f}, accuracy={acc:.4f}). "
            "Not starting/continuing the full run because benign/covert text is still too source-separable."
        )


def trace_quality_report(sender_dir: Path, report_path: Path) -> Dict[str, Any]:
    files = sorted(sender_dir.glob("*.jsonl"))
    artifact_action: Dict[str, int] = {}
    backticks = urls = code_fences = newlines = total_text = 0
    examples: List[Dict[str, Any]] = []
    for path in files[:200]:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                text = str(obj.get("semantic_text") or "")
                if text:
                    total_text += 1
                    artifact_action[f"{obj.get('artifact_class')}:{obj.get('action')}"] = artifact_action.get(f"{obj.get('artifact_class')}:{obj.get('action')}", 0) + 1
                    backticks += "`" in text
                    urls += bool(re.search(r"https?://|github\.com/", text, re.I))
                    code_fences += "```" in text
                    newlines += "\n" in text
                    if len(examples) < 20:
                        examples.append({
                            "file": path.name,
                            "artifact_class": obj.get("artifact_class"),
                            "action": obj.get("action"),
                            "text": text[:600],
                        })
    report = {
        "sender_files_seen": len(files),
        "text_events_scanned": total_text,
        "artifact_action_counts": artifact_action,
        "rates": {
            "backtick": backticks / total_text if total_text else 0.0,
            "url": urls / total_text if total_text else 0.0,
            "code_fence": code_fences / total_text if total_text else 0.0,
            "newline": newlines / total_text if total_text else 0.0,
        },
        "examples": examples,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2)[:4000])
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path, default=Path("experiments/colab_full_run"))
    parser.add_argument("--target-traces", type=int, default=4000)
    parser.add_argument("--min-traces", type=int, default=3500)
    parser.add_argument("--smoke-traces", type=int, default=25)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--skip-generation", action="store_true")
    parser.add_argument("--skip-ablation", action="store_true")
    parser.add_argument("--bert-epochs", type=int, default=3)
    parser.add_argument("--bert-max-samples", type=int, default=10000)
    parser.add_argument("--skip-semantic-smoke-gate", action="store_true")
    parser.add_argument("--semantic-smoke-max-auc", type=float, default=0.98)
    parser.add_argument("--semantic-smoke-max-accuracy", type=float, default=0.95)
    args = parser.parse_args()

    root = args.root.resolve()
    out = args.output_root if args.output_root.is_absolute() else root / args.output_root
    out.mkdir(parents=True, exist_ok=True)
    log_dir = out / "logs"

    assert_env()
    assert_inputs(root)

    print("DeployStega Colab full run")
    print(f"root={root}")
    print(f"output={out}")
    print(f"deployment={os.environ.get('AZURE_OPENAI_DEPLOYMENT') or os.environ.get('AZURE_OPENAI_DEPLOYMENT_NAME')}")
    print(f"api_version={os.environ.get('AZURE_OPENAI_API_VERSION')}")

    smoke_dir = out / "smoke_traces"
    full_dir = out / "covert_traces_full"

    if not args.skip_generation:
        if smoke_dir.exists():
            shutil.rmtree(smoke_dir)
        run([
            sys.executable, "scripts/generate_covert_traces.py",
            "--secrets-dir", "secrets",
            "--output-dir", str(smoke_dir),
            "--behavior-priors", "behavior_priors.json",
            "--feasibility-dir", "benign_traces",
            "--manifest", "experiments/experiment_manifest.json",
            "--num-traces", str(args.smoke_traces),
            "--workers", "1",
            "--seed", "123",
            "--max-secret-chunks", "20",
            "--estimated-bytes-per-chunk", "12",
        ], cwd=root, log_path=log_dir / "01_smoke_generation.log")

        smoke_summary = json.loads((smoke_dir / "generation_summary.json").read_text())
        if smoke_summary.get("verification_metrics", {}).get("verification_success_rate") != 1.0:
            raise SystemExit("Smoke generation failed token-binning verification; not starting full run.")
        trace_quality_report(smoke_dir / "sender", out / "smoke_quality_report.json")
        smoke_semantic_report = tfidf_source_diagnostic(
            root / "benign_traces",
            smoke_dir / "sender",
            out / "smoke_semantic_source_diagnostic.json",
            max_samples_per_class=2500,
            seed=123,
            repeats=5,
        )
        if not args.skip_semantic_smoke_gate:
            enforce_semantic_source_gate(
                smoke_semantic_report,
                max_auc=args.semantic_smoke_max_auc,
                max_accuracy=args.semantic_smoke_max_accuracy,
                label="Smoke",
            )

        full_dir.mkdir(parents=True, exist_ok=True)
        run([
            sys.executable, "scripts/generate_covert_traces.py",
            "--secrets-dir", "secrets",
            "--output-dir", str(full_dir),
            "--behavior-priors", "behavior_priors.json",
            "--feasibility-dir", "benign_traces",
            "--manifest", "experiments/experiment_manifest.json",
            "--num-traces", str(args.target_traces),
            "--workers", str(args.workers),
            "--seed", "42",
            "--estimated-bytes-per-chunk", "12",
            "--min-secret-keep-rate", "0.95",
        ], cwd=root, log_path=log_dir / "02_full_generation.log")

        run([
            sys.executable, "scripts/remove_semantic_backticks.py", str(full_dir),
            "--summary-path", str(full_dir / "backtick_cleanup_summary.json"),
        ], cwd=root, log_path=log_dir / "03_backtick_cleanup.log")

    sender_count = count_files(full_dir / "sender", "*.jsonl")
    receiver_count = count_files(full_dir / "receiver", "*.jsonl")
    print(f"Trace counts: sender={sender_count}, receiver={receiver_count}")
    if sender_count < args.min_traces or receiver_count < args.min_traces:
        raise SystemExit(f"Need at least {args.min_traces} trace pairs; got sender={sender_count}, receiver={receiver_count}")

    trace_quality_report(full_dir / "sender", out / "full_quality_report.json")
    full_semantic_report = tfidf_source_diagnostic(
        root / "benign_traces",
        full_dir / "sender",
        out / "full_semantic_source_diagnostic.json",
        max_samples_per_class=2500,
        seed=42,
        repeats=5,
    )
    if not args.skip_semantic_smoke_gate:
        enforce_semantic_source_gate(
            full_semantic_report,
            max_auc=args.semantic_smoke_max_auc,
            max_accuracy=args.semantic_smoke_max_accuracy,
            label="Full generation",
        )

    if not args.skip_ablation:
        ablation_out = out / "ablation_results"
        run([
            sys.executable, "scripts/run_ablation.py",
            "--benign-dir", "benign_traces",
            "--covert-dir", str(full_dir / "sender"),
            "--manifest", "experiments/experiment_manifest.json",
            "--output-root", str(ablation_out),
            "--target-fpr", "0.05",
            "--test-size", "0.3",
            "--validation-size", "0.2",
            "--seed", "42",
            "--workers", "1",
            "--user-key", "role_epoch",
            "--group-key", "experiment_id",
            "--include-bert",
            "--max-samples", str(args.bert_max_samples),
            "--bert-epochs", str(args.bert_epochs),
            "--bert-batch-size", "16",
            "--bert-max-length", "128",
            "--no-structural-parity",
        ], cwd=root, log_path=log_dir / "04_ablation.log")

    print("DONE. Results are in:", out)


if __name__ == "__main__":
    main()
