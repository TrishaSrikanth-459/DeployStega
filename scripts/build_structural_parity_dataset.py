#!/usr/bin/env python3
"""Build structurally paired benign/covert trace inputs for adversarial eval.

This addresses the generator-gap failure mode: classifiers should not separate
benign D from covert D' using trace length, role labels, repo namespaces,
identifier distributions, revisit rates, action-key presence, or time anchors.

For each pair, both output files use the same benign carrier event sequence.
Both benign and covert output semantic text are drawn only from original benign
trace rows. The benign file keeps text from its benign carrier when present;
the covert file receives length-matched text sampled from the original benign
trace text pool. Structural routing fields are otherwise identical.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

TEXT_FILES = [
    "gharchive_clean.csv",
    "imdb_clean.csv",
    "twitter_clean.csv",
    "combined.txt",
]

DROP_KEYS = {
    "experiment_id",
    "semantic_label",
    "semantic_content_type",
    "semantic_meaning",
    "semantic_ref",
    "role",
    "metadata",
}


def _load_jsonl_events(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
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
                rows.append(obj)
    return rows


def _usable_files(directory: Path) -> List[Path]:
    return [path for path in sorted(directory.glob("*.jsonl")) if _load_jsonl_events(path)]


def _load_cover_texts(project_root: Path) -> List[str]:
    texts: List[str] = []
    for name in TEXT_FILES:
        path = project_root / name
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                text = line.strip()
                if len(text) >= 20:
                    texts.append(text[:2000])
    if not texts:
        texts = [
            "Reviewed the change and left a concise note about the implementation details.",
            "Checked the repository activity and confirmed the issue discussion is routine.",
            "Updated the thread with a normal maintenance comment for future reference.",
        ]
    return texts


def _extract_payload_texts(events: Iterable[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for event in events:
        for key in ("semantic_text", "text", "body", "message", "content", "title"):
            value = event.get(key)
            if value is not None and str(value).strip():
                out.append(str(value).strip()[:4000])
                break
    return out


def _load_original_benign_texts(benign_files: Sequence[Path]) -> List[str]:
    texts: List[str] = []
    for path in benign_files:
        texts.extend(_extract_payload_texts(_load_jsonl_events(path)))
    return [text for text in texts if text and text.strip()]


def _build_length_buckets(texts: Sequence[str], bucket_size: int = 100) -> Dict[int, List[str]]:
    buckets: Dict[int, List[str]] = {}
    for text in texts:
        if not text:
            continue
        buckets.setdefault(max(0, len(text) // bucket_size), []).append(text)
    return buckets


def _sample_length_matched_text(
    texts: Sequence[str],
    buckets: Dict[int, List[str]],
    target_len: int,
    rng: random.Random,
    forbidden: Optional[Set[str]] = None,
    bucket_size: int = 100,
) -> str:
    forbidden = forbidden or set()
    if not texts:
        return "Reviewed the change and left a concise note about the implementation details."

    target_bucket = max(0, target_len // bucket_size)
    max_radius = max(8, max(buckets.keys(), default=0) + 1)
    for radius in range(max_radius + 1):
        candidate_buckets = [target_bucket] if radius == 0 else [target_bucket - radius, target_bucket + radius]
        candidates: List[str] = []
        for bucket in candidate_buckets:
            if bucket in buckets:
                candidates.extend(t for t in buckets[bucket] if t not in forbidden)
        if candidates:
            return rng.choice(candidates)

    candidates = [t for t in texts if t not in forbidden]
    return rng.choice(candidates or list(texts))


def _payload_slot_text(
    primary_texts: Sequence[str],
    fallback_texts: Sequence[str],
    fallback_buckets: Dict[int, List[str]],
    slot: int,
    rng: random.Random,
    target_len: Optional[int] = None,
    forbidden: Optional[Set[str]] = None,
) -> str:
    if slot < len(primary_texts):
        text = primary_texts[slot]
        if text and (not forbidden or text not in forbidden):
            return text

    if target_len is None:
        if primary_texts:
            target_len = len(primary_texts[slot % len(primary_texts)])
        else:
            target_len = len(rng.choice(list(fallback_texts))) if fallback_texts else 100
    return _sample_length_matched_text(fallback_texts, fallback_buckets, target_len, rng, forbidden)


def _normalize_carrier_event(event: Dict[str, Any], pair_id: str, idx: int, role: str) -> Dict[str, Any]:
    out = {k: v for k, v in event.items() if k not in DROP_KEYS and not k.startswith("semantic_")}
    out["role"] = role
    out["user_key"] = pair_id
    out["source_trace_id"] = pair_id
    out["epoch"] = int(out.get("epoch", idx))
    if "action" in out and "action_type" not in out:
        out["action_type"] = out["action"]
    elif "action_type" in out and "action" not in out:
        out["action"] = out["action_type"]
    else:
        out.setdefault("action", "view")
        out.setdefault("action_type", out["action"])
    out["semantic_content_type"] = "GitHubText"
    return out


def build_structural_parity_dataset(
    benign_dir: str | Path,
    covert_dir: str | Path,
    out_root: str | Path,
    *,
    project_root: str | Path,
    seed: int = 42,
    max_pairs: Optional[int] = None,
    max_events_per_file: Optional[int] = 200,
    role: str = "sender",
    text_mode: str = "benign_trace",
    overwrite: bool = True,
) -> Tuple[Path, Path, Dict[str, Any]]:
    benign_dir = Path(benign_dir)
    covert_dir = Path(covert_dir)
    out_root = Path(out_root)
    project_root = Path(project_root)
    benign_out = out_root / "benign"
    covert_out = out_root / "covert"

    if overwrite and out_root.exists():
        shutil.rmtree(out_root)
    benign_out.mkdir(parents=True, exist_ok=True)
    covert_out.mkdir(parents=True, exist_ok=True)

    benign_files = _usable_files(benign_dir)
    covert_files = _usable_files(covert_dir)
    if not benign_files:
        raise ValueError(f"No usable benign JSONL files found in {benign_dir}")
    if not covert_files:
        raise ValueError(f"No usable covert JSONL files found in {covert_dir}")

    rng = random.Random(seed)
    rng.shuffle(benign_files)
    rng.shuffle(covert_files)
    pair_count = min(len(benign_files), len(covert_files))
    if max_pairs is not None:
        pair_count = min(pair_count, int(max_pairs))

    if text_mode == "corpus_cover":
        text_mode = "benign_trace"
    if text_mode not in {"benign_trace", "generated_pool"}:
        raise ValueError(f"Unsupported text_mode={text_mode!r}; expected benign_trace or generated_pool")

    original_benign_text_pool = _load_original_benign_texts(benign_files)
    if not original_benign_text_pool:
        raise ValueError("No text fields found in original benign traces; cannot build benign-only semantic parity data")
    benign_buckets = _build_length_buckets(original_benign_text_pool)

    # Diagnostic-only mode kept for controlled debugging, never used by the main run.
    covert_payloads_by_path: Dict[Path, List[str]] = {}
    generated_text_pool: List[str] = []
    generated_buckets: Dict[int, List[str]] = {}
    if text_mode == "generated_pool":
        cover_texts = _load_cover_texts(project_root)
        covert_payloads_by_path = {path: _extract_payload_texts(_load_jsonl_events(path)) for path in covert_files}
        generated_text_pool = [text for payloads in covert_payloads_by_path.values() for text in payloads]
        if not generated_text_pool:
            generated_text_pool = cover_texts
        generated_buckets = _build_length_buckets(generated_text_pool)

    manifest: List[Dict[str, Any]] = []

    for i in range(pair_count):
        pair_id = f"parity_{i:06d}"
        carrier_path = benign_files[i % len(benign_files)]
        payload_path = covert_files[i % len(covert_files)]
        benign_payload_path = covert_files[(i + max(1, pair_count // 2)) % len(covert_files)]
        if benign_payload_path == payload_path and len(covert_files) > 1:
            benign_payload_path = covert_files[(i + 1) % len(covert_files)]
        source_carrier_events = _load_jsonl_events(carrier_path)
        if max_events_per_file is not None and max_events_per_file > 0:
            carrier_events = source_carrier_events[: int(max_events_per_file)]
        else:
            carrier_events = source_carrier_events
        payload_texts: List[str] = []
        benign_payload_texts: List[str] = []
        if text_mode == "generated_pool":
            payload_texts = covert_payloads_by_path.get(payload_path, [])
            benign_payload_texts = covert_payloads_by_path.get(benign_payload_path, [])
            if not payload_texts:
                payload_texts = [_sample_length_matched_text(generated_text_pool, generated_buckets, 250, rng)]
            if not benign_payload_texts:
                benign_payload_texts = [_sample_length_matched_text(generated_text_pool, generated_buckets, len(payload_texts[0]), rng)]

        benign_rows: List[Dict[str, Any]] = []
        covert_rows: List[Dict[str, Any]] = []
        for j, carrier in enumerate(carrier_events):
            base = _normalize_carrier_event(carrier, pair_id, j, role)
            benign = dict(base)
            covert = dict(base)
            carrier_texts = _extract_payload_texts([carrier])
            carrier_text = carrier_texts[0] if carrier_texts else _sample_length_matched_text(
                original_benign_text_pool, benign_buckets, 250, rng
            )

            if text_mode == "benign_trace":
                benign_text = carrier_text
                covert_text = _sample_length_matched_text(
                    original_benign_text_pool,
                    benign_buckets,
                    len(benign_text),
                    rng,
                    forbidden={benign_text},
                )
            else:
                # Diagnostic-only mode: useful to prove semantic-source leakage,
                # but not appropriate for the main experiment because controls
                # are sampled from generated/covert text rather than benign traces.
                covert_text = _payload_slot_text(
                    payload_texts,
                    generated_text_pool,
                    generated_buckets,
                    j,
                    rng,
                    target_len=len(payload_texts[j % len(payload_texts)]) if payload_texts else None,
                )
                benign_text = _payload_slot_text(
                    benign_payload_texts,
                    generated_text_pool,
                    generated_buckets,
                    j,
                    rng,
                    target_len=len(covert_text),
                    forbidden={covert_text},
                )
                if abs(len(benign_text) - len(covert_text)) > 200:
                    benign_text = _sample_length_matched_text(
                        generated_text_pool, generated_buckets, len(covert_text), rng, forbidden={covert_text}
                    )

            benign["semantic_text"] = benign_text
            covert["semantic_text"] = covert_text
            benign_rows.append(benign)
            covert_rows.append(covert)

        benign_path = benign_out / f"{pair_id}.jsonl"
        covert_path = covert_out / f"{pair_id}.jsonl"
        with benign_path.open("w", encoding="utf-8") as f:
            for row in benign_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        with covert_path.open("w", encoding="utf-8") as f:
            for row in covert_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        manifest.append({
            "pair_id": pair_id,
            "benign_carrier": str(carrier_path),
            "covert_reference_file": str(payload_path),
            "events": len(carrier_events),
            "source_events": len(source_carrier_events),
            "semantic_text_source": "original_benign_traces" if text_mode == "benign_trace" else "generated_pool_diagnostic",
            "covert_payload_texts": len(payload_texts),
            "benign_payload_texts": len(benign_payload_texts),
        })

    summary = {
        "pair_count": pair_count,
        "benign_input_files": len(benign_files),
        "covert_input_files": len(covert_files),
        "benign_out": str(benign_out),
        "covert_out": str(covert_out),
        "role": role,
        "seed": seed,
        "max_events_per_file": max_events_per_file,
        "text_mode": text_mode,
        "original_benign_text_pool_size": len(original_benign_text_pool),
        "generated_text_pool_size": len(generated_text_pool),
        "semantic_text_source": "original_benign_traces" if text_mode == "benign_trace" else "generated_pool_diagnostic",
        "note": "Main mode: both benign and covert semantic_text are sampled only from original benign trace text; structural carrier traces are identical.",
    }
    with (out_root / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump({"summary": summary, "pairs": manifest}, f, indent=2)
    return benign_out, covert_out, summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Build structurally paired evaluation inputs")
    ap.add_argument("--benign-dir", required=True)
    ap.add_argument("--covert-dir", required=True)
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--project-root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-pairs", type=int, default=None, help="Maximum paired files; 0 means no cap")
    ap.add_argument("--max-events-per-file", type=int, default=200, help="Maximum carrier events per paired file; 0 means no cap")
    ap.add_argument("--text-mode", choices=["benign_trace", "generated_pool", "corpus_cover"], default="benign_trace")
    ap.add_argument("--role", default="sender")
    args = ap.parse_args()
    _benign, _covert, summary = build_structural_parity_dataset(
        args.benign_dir,
        args.covert_dir,
        args.out_root,
        project_root=args.project_root,
        seed=args.seed,
        max_pairs=None if args.max_pairs == 0 else args.max_pairs,
        max_events_per_file=None if args.max_events_per_file == 0 else args.max_events_per_file,
        role=args.role,
        text_mode=args.text_mode,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
