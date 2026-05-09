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
from typing import Any, Dict, Iterable, List

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
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--skip-generation", action="store_true")
    parser.add_argument("--skip-ablation", action="store_true")
    parser.add_argument("--bert-epochs", type=int, default=3)
    parser.add_argument("--bert-max-samples", type=int, default=10000)
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
            "--num-traces", "3",
            "--workers", "1",
            "--seed", "123",
            "--max-secret-chunks", "20",
            "--estimated-bytes-per-chunk", "12",
        ], cwd=root, log_path=log_dir / "01_smoke_generation.log")

        smoke_summary = json.loads((smoke_dir / "generation_summary.json").read_text())
        if smoke_summary.get("verification_metrics", {}).get("verification_success_rate") != 1.0:
            raise SystemExit("Smoke generation failed token-binning verification; not starting full run.")
        trace_quality_report(smoke_dir / "sender", out / "smoke_quality_report.json")

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
