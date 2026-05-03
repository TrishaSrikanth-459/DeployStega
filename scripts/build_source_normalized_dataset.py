#!/usr/bin/env python3
"""Build source-leak-controlled DeployStega evaluation inputs.

The goal is not to make benign and covert traces identical. The goal is to keep
original benign events/text and original covert events/text while removing
trivial source tells that let a detector learn which generator produced a file.

Default mode (`common_support`) constructs paired trace slices from the common
support of the two datasets:

- every output file has the same number of events;
- every event has real text from its original class;
- benign and covert paired files share the same artifact/action pattern;
- repeated-access/revisit structure is matched by using same-identifier chunks;
- role/schema/semantic labels/time anchors are normalized;
- benign text length is matched as closely as possible to covert text length.

This preserves the important comparison: original benign GitHub text/routing vs
original covert stego text/routing, without allowing empty-text, trace-length,
role, artifact-class, or timestamp-anchor source leakage to dominate epsilon.
"""
from __future__ import annotations

import argparse
import bisect
import json
import random
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

TEXT_KEYS = ("semantic_text", "text", "body", "message", "content", "title")
COMMON_SEMANTIC_CONTENT_TYPE = "GitHubText"
COMMON_ROLE = "user"
COMMON_TIME_ORIGIN = 1700000000.0
DEFAULT_COMMON_PATTERNS = (("PullRequest", "edit"), ("Issue", "edit"))


@dataclass(frozen=True)
class EventRef:
    source: Path
    event: Dict[str, Any]
    text: str
    pattern: Tuple[str, str]
    identifier: Tuple[Any, ...]
    timestamp: Optional[float]
    source_index: int


@dataclass(frozen=True)
class Chunk:
    source: Path
    events: Tuple[EventRef, ...]
    pattern: Tuple[str, str]
    source_group: str

    @property
    def text_len(self) -> int:
        return sum(len(e.text) for e in self.events)

    @property
    def per_event_lengths(self) -> Tuple[int, ...]:
        return tuple(len(e.text) for e in self.events)


def _parse_timestamp(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return float(raw)
    except Exception:
        pass
    iso = raw.replace(" UTC", "+00:00")
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(iso).timestamp()
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S UTC", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            continue
    return None


def _extract_text(event: Dict[str, Any], max_chars: int = 4000) -> str:
    for key in TEXT_KEYS:
        value = event.get(key)
        if value is not None and str(value).strip():
            return str(value).replace("\x00", "").strip()[:max_chars]
    return ""


def _load_events(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
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
            if "epoch" in obj and ("identifier" in obj or "url" in obj):
                rows.append(obj)
    return rows


def _identifier(event: Dict[str, Any]) -> Tuple[Any, ...]:
    raw = event.get("identifier", event.get("repo"))
    if isinstance(raw, tuple):
        return raw
    if isinstance(raw, list):
        return tuple(raw)
    if raw is not None:
        return (raw,)
    url = str(event.get("url") or "unknown")
    return (url,)


def _pattern(event: Dict[str, Any]) -> Tuple[str, str]:
    artifact_class = str(event.get("artifact_class") or event.get("artifactClass") or "Repository").strip() or "Repository"
    action = str(event.get("action_type") or event.get("actionType") or event.get("action") or "view").strip() or "view"
    return artifact_class, action


def _url(event: Dict[str, Any]) -> str:
    url = str(event.get("url") or "").strip()
    if url:
        return url
    return "https://github.com/" + "/".join(str(x) for x in _identifier(event))


def _event_refs(path: Path, allowed_patterns: set[Tuple[str, str]]) -> List[EventRef]:
    refs: List[EventRef] = []
    for idx, event in enumerate(_load_events(path)):
        pat = _pattern(event)
        if pat not in allowed_patterns:
            continue
        text = _extract_text(event)
        if not text:
            continue
        refs.append(
            EventRef(
                source=path,
                event=event,
                text=text,
                pattern=pat,
                identifier=_identifier(event),
                timestamp=_parse_timestamp(event.get("timestamp")),
                source_index=idx,
            )
        )
    return refs


def _chunks_from_file(
    path: Path,
    *,
    class_name: str,
    allowed_patterns: set[Tuple[str, str]],
    events_per_file: int,
) -> List[Chunk]:
    refs = _event_refs(path, allowed_patterns)
    grouped: Dict[Tuple[Tuple[str, str], Tuple[Any, ...]], List[EventRef]] = defaultdict(list)
    for ref in refs:
        grouped[(ref.pattern, ref.identifier)].append(ref)

    chunks: List[Chunk] = []
    for (pat, _ident), items in grouped.items():
        items = sorted(items, key=lambda r: (r.timestamp if r.timestamp is not None else float("inf"), r.source_index))
        for start in range(0, len(items) - events_per_file + 1, events_per_file):
            piece = tuple(items[start : start + events_per_file])
            if len(piece) == events_per_file:
                chunks.append(
                    Chunk(
                        source=path,
                        events=piece,
                        pattern=pat,
                        source_group=f"{class_name}:{path.stem}",
                    )
                )
    return chunks


def _collect_chunks(
    directory: Path,
    *,
    class_name: str,
    allowed_patterns: set[Tuple[str, str]],
    events_per_file: int,
) -> List[Chunk]:
    chunks: List[Chunk] = []
    for path in sorted(directory.glob("*.jsonl")):
        chunks.extend(
            _chunks_from_file(
                path,
                class_name=class_name,
                allowed_patterns=allowed_patterns,
                events_per_file=events_per_file,
            )
        )
    return chunks


def _chunk_distance(a: Chunk, b: Chunk) -> int:
    # Text length is an easy semantic source tell, so match both total and per-event lengths.
    total = abs(a.text_len - b.text_len)
    per_event = sum(abs(x - y) for x, y in zip(a.per_event_lengths, b.per_event_lengths))
    return total + per_event


def _match_chunks(
    benign_chunks: Sequence[Chunk],
    covert_chunks: Sequence[Chunk],
    *,
    seed: int,
    max_pairs: Optional[int],
) -> List[Tuple[Chunk, Chunk]]:
    rng = random.Random(seed)
    benign_by_pattern: Dict[Tuple[str, str], List[Chunk]] = defaultdict(list)
    for chunk in benign_chunks:
        benign_by_pattern[chunk.pattern].append(chunk)
    for chunks in benign_by_pattern.values():
        chunks.sort(key=lambda c: c.text_len)

    covert_order = list(covert_chunks)
    rng.shuffle(covert_order)
    covert_order.sort(key=lambda c: (c.pattern, c.text_len))

    pairs: List[Tuple[Chunk, Chunk]] = []
    for covert in covert_order:
        candidates = benign_by_pattern.get(covert.pattern) or []
        if not candidates:
            continue
        lengths = [c.text_len for c in candidates]
        pos = bisect.bisect_left(lengths, covert.text_len)
        search_positions = list(range(max(0, pos - 8), min(len(candidates), pos + 9)))
        if not search_positions:
            search_positions = [min(pos, len(candidates) - 1)]
        best_i = min(search_positions, key=lambda i: _chunk_distance(candidates[i], covert))
        benign = candidates.pop(best_i)
        pairs.append((benign, covert))
        if max_pairs is not None and len(pairs) >= max_pairs:
            break
    return pairs


def _normalized_event(ref: EventRef, idx: int, group_key: str, *, fixed_timing: bool) -> Dict[str, Any]:
    if fixed_timing:
        timestamp = COMMON_TIME_ORIGIN + float(idx * 60)
    else:
        first_ts = ref.timestamp
        timestamp = COMMON_TIME_ORIGIN + float(idx * 60) if first_ts is None else COMMON_TIME_ORIGIN + max(0.0, ref.timestamp - first_ts)
    artifact_class, action = ref.pattern
    return {
        "artifact_class": artifact_class,
        "action": action,
        "action_type": action,
        "timestamp": timestamp,
        "identifier": list(ref.identifier),
        "url": _url(ref.event),
        "epoch": idx,
        "role": COMMON_ROLE,
        "user_key": group_key,
        "semantic_content_type": COMMON_SEMANTIC_CONTENT_TYPE,
        "semantic_text": ref.text,
    }


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _parse_patterns(raw: str) -> Tuple[Tuple[str, str], ...]:
    if not raw.strip():
        return DEFAULT_COMMON_PATTERNS
    patterns = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"Pattern must be ArtifactClass:action, got {item!r}")
        artifact, action = item.split(":", 1)
        patterns.append((artifact.strip(), action.strip()))
    return tuple(patterns)


def _summarize_output(directory: Path) -> Dict[str, Any]:
    event_counts: Counter[int] = Counter()
    text_counts: Counter[int] = Counter()
    patterns: Counter[Tuple[str, str]] = Counter()
    revisit_unique: Counter[int] = Counter()
    text_lens: List[int] = []
    groups: Counter[str] = Counter()
    for path in sorted(directory.glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        event_counts[len(rows)] += 1
        text_counts[sum(1 for row in rows if row.get("semantic_text"))] += 1
        groups[str(rows[0].get("user_key")) if rows else ""] += 1
        ids = set()
        for row in rows:
            patterns[(str(row.get("artifact_class")), str(row.get("action")))] += 1
            ids.add(tuple(row.get("identifier", [])))
            text_lens.append(len(str(row.get("semantic_text") or "")))
        revisit_unique[len(ids)] += 1
    return {
        "files": sum(event_counts.values()),
        "event_counts": dict(sorted(event_counts.items())),
        "text_counts": dict(sorted(text_counts.items())),
        "patterns": {f"{k[0]}:{k[1]}": v for k, v in sorted(patterns.items())},
        "unique_identifier_counts": dict(sorted(revisit_unique.items())),
        "source_groups": len(groups),
        "text_len_min": min(text_lens) if text_lens else 0,
        "text_len_mean": round(sum(text_lens) / len(text_lens), 3) if text_lens else 0,
        "text_len_max": max(text_lens) if text_lens else 0,
    }


def build_source_normalized_dataset(
    benign_dir: str | Path,
    covert_dir: str | Path,
    out_root: str | Path,
    *,
    seed: int = 42,
    max_files_per_class: Optional[int] = None,
    max_events_per_file: Optional[int] = None,
    overwrite: bool = True,
    common_patterns: Sequence[Tuple[str, str]] = DEFAULT_COMMON_PATTERNS,
    fixed_timing: bool = True,
) -> Tuple[Path, Path, Dict[str, Any]]:
    """Build a common-support source-normalized paired dataset.

    max_files_per_class is retained for backward compatibility with older calls;
    it now means max matched pairs. max_events_per_file is retained as the fixed
    output events per file, defaulting to 2 when omitted.
    """
    benign_dir = Path(benign_dir)
    covert_dir = Path(covert_dir)
    out_root = Path(out_root)
    benign_out = out_root / "benign"
    covert_out = out_root / "covert"

    if overwrite and out_root.exists():
        shutil.rmtree(out_root)
    benign_out.mkdir(parents=True, exist_ok=True)
    covert_out.mkdir(parents=True, exist_ok=True)

    events_per_file = max_events_per_file if max_events_per_file and max_events_per_file > 0 else 2
    allowed_patterns = set(common_patterns)

    benign_chunks = _collect_chunks(
        benign_dir,
        class_name="benign",
        allowed_patterns=allowed_patterns,
        events_per_file=events_per_file,
    )
    covert_chunks = _collect_chunks(
        covert_dir,
        class_name="covert",
        allowed_patterns=allowed_patterns,
        events_per_file=events_per_file,
    )
    if not benign_chunks:
        raise ValueError(f"No eligible benign chunks found in {benign_dir}")
    if not covert_chunks:
        raise ValueError(f"No eligible covert chunks found in {covert_dir}")

    max_pairs = max_files_per_class if max_files_per_class and max_files_per_class > 0 else None
    pairs = _match_chunks(benign_chunks, covert_chunks, seed=seed, max_pairs=max_pairs)
    if not pairs:
        raise ValueError("No matched benign/covert chunks found on common support")

    rng = random.Random(seed)
    rng.shuffle(pairs)

    manifest: Dict[str, Any] = {
        "summary": {
            "normalization": "source_normalized_common_support",
            "semantic_text_policy": "preserve_original_class_text_require_text_in_all_events",
            "routing_policy": "preserve_original_events_on_common_artifact_action_revisit_support",
            "matching": "same event count, same artifact/action pattern, same repeated-artifact structure, nearest benign text length",
            "fixed_timing": fixed_timing,
            "events_per_file": events_per_file,
            "common_patterns": [f"{a}:{b}" for a, b in common_patterns],
            "benign_candidate_chunks": len(benign_chunks),
            "covert_candidate_chunks": len(covert_chunks),
            "matched_pairs": len(pairs),
            "seed": seed,
            "removed_leakage": [
                "empty benign text vs non-empty covert text",
                "trace length / total_events",
                "artifact/action class outside common support",
                "identifier revisit-count imbalance",
                "role constants",
                "class-specific JSON key presence",
                "experiment_id/semantic labels/source metadata",
                "absolute timestamp anchors and generator-specific timing deltas" if fixed_timing else "absolute timestamp anchors",
                "source-specific semantic_content_type",
            ],
        },
        "pairs": [],
    }

    for idx, (benign, covert) in enumerate(pairs):
        benign_dst = benign_out / f"benign_{idx:06d}.jsonl"
        covert_dst = covert_out / f"covert_{idx:06d}.jsonl"
        benign_rows = [
            _normalized_event(ref, event_idx, benign.source_group, fixed_timing=fixed_timing)
            for event_idx, ref in enumerate(benign.events)
        ]
        covert_rows = [
            _normalized_event(ref, event_idx, covert.source_group, fixed_timing=fixed_timing)
            for event_idx, ref in enumerate(covert.events)
        ]
        _write_jsonl(benign_dst, benign_rows)
        _write_jsonl(covert_dst, covert_rows)
        manifest["pairs"].append(
            {
                "index": idx,
                "pattern": f"{benign.pattern[0]}:{benign.pattern[1]}",
                "benign_source": str(benign.source),
                "covert_source": str(covert.source),
                "benign_text_len": benign.text_len,
                "covert_text_len": covert.text_len,
                "text_len_abs_diff": abs(benign.text_len - covert.text_len),
            }
        )

    manifest["summary"]["benign_output"] = _summarize_output(benign_out)
    manifest["summary"]["covert_output"] = _summarize_output(covert_out)
    diffs = [p["text_len_abs_diff"] for p in manifest["pairs"]]
    manifest["summary"]["text_length_match"] = {
        "mean_abs_diff": round(sum(diffs) / len(diffs), 3),
        "max_abs_diff": max(diffs),
    }

    with (out_root / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return benign_out, covert_out, manifest["summary"]


def main() -> None:
    ap = argparse.ArgumentParser(description="Build source-normalized common-support evaluation inputs")
    ap.add_argument("--benign-dir", required=True)
    ap.add_argument("--covert-dir", required=True)
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-files-per-class", type=int, default=0, help="Max matched pairs; 0 means no cap")
    ap.add_argument("--max-events-per-file", type=int, default=2, help="Fixed events per output file")
    ap.add_argument("--common-patterns", default=",".join(f"{a}:{b}" for a, b in DEFAULT_COMMON_PATTERNS))
    ap.add_argument("--preserve-timing", action="store_true", help="Preserve source timing deltas instead of using fixed matched timing")
    args = ap.parse_args()
    _benign, _covert, summary = build_source_normalized_dataset(
        args.benign_dir,
        args.covert_dir,
        args.out_root,
        seed=args.seed,
        max_files_per_class=None if args.max_files_per_class == 0 else args.max_files_per_class,
        max_events_per_file=args.max_events_per_file,
        common_patterns=_parse_patterns(args.common_patterns),
        fixed_timing=not args.preserve_timing,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
