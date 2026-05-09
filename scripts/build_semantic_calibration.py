#!/usr/bin/env python3
"""Build a held-out benign style calibration set for covert text generation.

This script supports the research-valid path for reducing semantic generator
mismatch:

* calibration examples come only from original benign traces;
* calibration files are excluded from the benign evaluation directory;
* only source-normalized PR/Issue edit prose is used as style reference;
* no covert/generated text is used to build the benign control.

The output exemplar JSONL is consumed by routing.semantic.stego_encoder through
STEGO_BENIGN_EXEMPLARS_PATH.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


TEXT_KEYS = ("semantic_text", "text", "body", "message", "content", "title")
COMPARABLE_ARTIFACTS = {"PullRequest", "Issue"}


def first_text_field(obj: Dict[str, Any]) -> str:
    for key in TEXT_KEYS:
        value = obj.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def infer_action(obj: Dict[str, Any], artifact_class: str, has_text: bool) -> str:
    raw = obj.get("action") or obj.get("action_type") or obj.get("actionType") or obj.get("event_type")
    if raw is not None:
        return str(raw).strip().lower()
    if artifact_class in COMPARABLE_ARTIFACTS and has_text:
        return "edit"
    return "view"


def normalize_style_text(text: Any) -> str:
    """Conservative source-format cleanup for style exemplars."""
    if text is None:
        return ""
    text = str(text).replace("\x00", " ")
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"\[([^\]]+)\]\((?:https?://|mailto:)[^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+|github\.com/\S+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", " ", text)

    cleaned: List[str] = []
    in_fence = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if re.search(r"\b(Co-authored-by|Reviewed-by|Signed-off-by|Pull Request resolved|Approved by)\b", line, re.I):
            continue
        if re.match(r"^\s*[-*+]\s+\[[ xX]\]\s*", line):
            continue
        line = re.sub(r"^\s*[-*+]\s+", "", line)
        line = re.sub(r"^\s*\d+[.)]\s+", "", line)
        line = re.sub(r"^\s*#+\s*", "", line)
        line = line.replace("`", "")
        line = re.sub(r"</?[^>]+>", " ", line)
        line = line.replace("|", " ")
        line = re.sub(r"\b[0-9a-f]{12,40}\b", " ", line, flags=re.I)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            cleaned.append(line)

    text = " ".join(cleaned)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def iter_comparable_texts(path: Path) -> Iterable[Tuple[str, str]]:
    with path.open("r", encoding="utf-8", errors="ignore") as f:
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
            artifact_class = str(obj.get("artifact_class") or obj.get("artifactClass") or "")
            if artifact_class not in COMPARABLE_ARTIFACTS:
                continue
            raw_text = first_text_field(obj)
            if not raw_text.strip():
                continue
            action = infer_action(obj, artifact_class, has_text=True)
            if action != "edit":
                continue
            text = normalize_style_text(raw_text)
            words = text.split()
            if not (6 <= len(words) <= 180):
                continue
            if sum(ch.isalpha() for ch in text) < 20:
                continue
            yield artifact_class, text


def select_calibration_files(files: Sequence[Path], count: int, seed: int) -> List[Path]:
    rng = random.Random(seed)
    shuffled = list(files)
    rng.shuffle(shuffled)
    if count <= 0:
        return []
    # Keep the calibration slice modest so evaluation remains large.
    cap = max(1, min(count, max(1, int(round(len(files) * 0.10)))))
    return sorted(shuffled[:cap])


def make_eval_dir(files: Sequence[Path], calibration_files: Set[Path], eval_dir: Path, copy_files: bool) -> int:
    if eval_dir.exists():
        shutil.rmtree(eval_dir)
    eval_dir.mkdir(parents=True, exist_ok=True)

    n = 0
    for src in files:
        if src in calibration_files:
            continue
        dst = eval_dir / src.name
        if copy_files:
            shutil.copy2(src, dst)
        else:
            try:
                os.symlink(src.resolve(), dst)
            except OSError:
                shutil.copy2(src, dst)
        n += 1
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benign-dir", type=Path, required=True)
    parser.add_argument("--eval-dir", type=Path, required=True)
    parser.add_argument("--exemplars-path", type=Path, required=True)
    parser.add_argument("--manifest-path", type=Path, required=True)
    parser.add_argument("--calibration-files", type=int, default=200)
    parser.add_argument("--max-exemplars-per-class", type=int, default=400)
    parser.add_argument("--seed", type=int, default=20260509)
    parser.add_argument("--copy-files", action="store_true")
    args = parser.parse_args()

    benign_files = sorted(args.benign_dir.glob("*.jsonl"))
    if not benign_files:
        raise SystemExit(f"No benign JSONL files found in {args.benign_dir}")

    calibration = select_calibration_files(benign_files, args.calibration_files, args.seed)
    calibration_set = set(calibration)
    eval_count = make_eval_dir(benign_files, calibration_set, args.eval_dir, args.copy_files)

    rng = random.Random(args.seed + 17)
    grouped: Dict[str, List[str]] = defaultdict(list)
    seen: Set[str] = set()
    for path in calibration:
        for artifact_class, text in iter_comparable_texts(path):
            key = re.sub(r"\W+", " ", text.lower()).strip()
            if key in seen:
                continue
            seen.add(key)
            grouped[artifact_class].append(text)

    args.exemplars_path.parent.mkdir(parents=True, exist_ok=True)
    written_counts: Counter[str] = Counter()
    with args.exemplars_path.open("w", encoding="utf-8") as out:
        for artifact_class in sorted(grouped):
            values = grouped[artifact_class]
            rng.shuffle(values)
            for text in values[: args.max_exemplars_per_class]:
                out.write(json.dumps({"artifact_class": artifact_class, "semantic_text": text}) + "\n")
                written_counts[artifact_class] += 1

    manifest = {
        "benign_dir": str(args.benign_dir),
        "eval_dir": str(args.eval_dir),
        "exemplars_path": str(args.exemplars_path),
        "seed": args.seed,
        "calibration_file_count": len(calibration),
        "evaluation_file_count": eval_count,
        "calibration_files": [p.name for p in calibration],
        "exemplar_counts": dict(written_counts),
        "methodology": (
            "Style exemplars are source-normalized PR/Issue edit texts from a "
            "held-out benign calibration slice. Those files are excluded from "
            "the benign evaluation directory."
        ),
    }
    args.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2)[:4000])


if __name__ == "__main__":
    main()
