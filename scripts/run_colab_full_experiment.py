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
import random
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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


def _extract_semantic_text(event: Dict[str, Any]) -> str:
    for key in ("artifact_text", "semantic_text", "text", "body", "message", "content", "title"):
        value = event.get(key) if isinstance(event, dict) else None
        if value is not None and str(value).strip():
            return str(value)
    return ""


def find_external_semantic_corpus(root: Path) -> Path:
    """Find the independent GitHub semantic corpus/parser artifact for bins.

    Important: token-bin vocabulary must not be learned from evaluation benign
    or covert traces. Accepted inputs are the weekly GitHub semantic corpus or
    corpus_parser outputs (corpus.json, valid_words.json, candidates.json, or an
    explicitly supplied bins_k*.json).
    """
    candidates: List[Path] = []
    env_path = os.environ.get("DEPLOYSTEGA_SEMANTIC_CORPUS") or os.environ.get("SEMANTIC_CORPUS_PATH")
    if env_path:
        candidates.append(Path(env_path))

    drive_data = Path("/content/drive/MyDrive/DeployStega_data")
    repo_bases = (root, root / "scripts", root / "data", root / "dataset")
    data_bases = (drive_data, drive_data / "scripts", drive_data / "data", drive_data / "token_binning_data")
    for base in repo_bases + data_bases:
        candidates.extend([
            base / "corpus.json",
            base / "semantic_corpus.jsonl",
            base / "github_semantic_corpus.jsonl",
            base / "valid_words.json",
            base / "candidates.json",
        ])
    # Only accept prebuilt bins automatically from the data mount, not the repo
    # default, so a missing weekly corpus cannot silently fall back to stale bins.
    candidates.extend([
        drive_data / "token_binning_data" / "bins_k16.json",
        drive_data / "token_binning_data" / "bins_k32.json",
        drive_data / "token_binning_data" / "bins_k64.json",
    ])

    for path in candidates:
        if path.exists() and path.is_file():
            return path

    searched = "\n".join(str(p) for p in candidates)
    raise SystemExit(
        "Missing independent semantic corpus/parser artifact for token-bin calibration. "
        "Do not build bins from benign_traces or covert traces. Provide the weekly "
        "GitHub semantic corpus as corpus.json/semantic_corpus.jsonl, a corpus_parser "
        "artifact such as valid_words.json/candidates.json, or set DEPLOYSTEGA_SEMANTIC_CORPUS.\n"
        f"Searched:\n{searched}"
    )


def _word_rows(items: Iterable[Any]) -> Iterable[Dict[str, Any]]:
    """Expose corpus_parser word lists/bins as one token row per word."""
    for item in items:
        if isinstance(item, str):
            yield {"artifact_text": item}
        elif isinstance(item, dict):
            value = item.get("word") or item.get("token") or item.get("text") or item.get("artifact_text")
            if value:
                yield {"artifact_text": str(value)}
        elif isinstance(item, list):
            yield from _word_rows(item)


def _corpus_rows(corpus_path: Path) -> Iterable[Dict[str, Any]]:
    """Yield rows from weekly corpus JSONL/JSON or corpus_parser artifacts."""
    with corpus_path.open("r", encoding="utf-8", errors="ignore") as f:
        first = f.read(1)
        f.seek(0)
        if first == "[":
            data = json.load(f)
            if isinstance(data, list):
                # A JSON array can be rows or a corpus_parser word list. Dicts
                # with semantic text stay rows; bare strings become word rows.
                for item in data:
                    if isinstance(item, dict) and _extract_semantic_text(item):
                        yield item
                    else:
                        yield from _word_rows([item])
            return
        if first == "{":
            try:
                data = json.load(f)
            except Exception:
                # Most weekly corpus exports are JSONL: one JSON object per
                # line. The first byte is still "{", so we must fall back to
                # streaming line-by-line instead of silently returning no rows.
                f.seek(0)
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(obj, dict):
                        yield obj
                    elif isinstance(obj, str):
                        yield {"artifact_text": obj}
                return
            if isinstance(data, dict):
                # corpus_parser / extraction artifacts can be nested in common keys.
                for key in ("rows", "records", "items", "data", "corpus"):
                    if isinstance(data.get(key), list):
                        for item in data[key]:
                            if isinstance(item, dict) and _extract_semantic_text(item):
                                yield item
                            else:
                                yield from _word_rows([item])
                        return
                for key in ("valid_words", "candidates", "words", "vocab", "tokens", "bins"):
                    if isinstance(data.get(key), list):
                        yield from _word_rows(data[key])
                        return
                if _extract_semantic_text(data):
                    yield data
            return
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                yield obj
            elif isinstance(obj, str):
                yield {"artifact_text": obj}


def _artifact_type_from_corpus_row(row: Dict[str, Any]) -> str:
    return str(
        row.get("artifact_type")
        or row.get("artifact_class")
        or row.get("artifactClass")
        or ""
    ).strip()


def _classify_corpus_text_style(text: str, artifact_type: str) -> str:
    """Classify independent corpus text into coarse aggregate style buckets.

    These are not label filters or benign-trace examples. They are aggregate
    buckets from the external GitHub corpus so the generator can match the
    *mixture* of real PR/issue body styles instead of collapsing into generic
    assistant-written review notes.
    """
    low = text.lower()
    if re.search(r"\bdependabot\b|\bbump(?:s|ed)?\b|\bdependency\b|\bdependencies\b|\bpackage\b|\brelease notes\b|\bchangelog\b", low):
        return "dependency_update"
    if re.search(r"\bbackport\b|\bcherry[- ]pick\b|\bcherry picked\b|\bfollowing commits\b|\bconflict(?:s|ing)?\b", low):
        return "backport_or_cherry_pick"
    if re.search(r"\bcodecov\b|\bcoverage\b|\bworkflow\b|\bci\b|\bgithub actions\b|\bbuild failed\b|\bstatus check\b", low):
        return "ci_or_coverage_report"
    if re.search(r"\brepro(?:duce|duction)?\b|\bexpected\b|\bactual\b|\bobserved\b|\bsteps to\b|\bstack trace\b|\berror\b|\bcrash\b|\bfailing\b", low):
        return "bug_repro_or_issue"
    if re.search(r"\breadme\b|\bdocs?\b|\bdocumentation\b|\bguide\b|\bexample\b|\btutorial\b", low):
        return "docs_or_example_update"
    if re.search(r"\brefactor\b|\bcleanup\b|\bchore\b|\brename\b|\bmove\b|\bremove\b|\bdeprecate\b", low):
        return "maintenance_or_refactor"
    if artifact_type == "Issue":
        return "issue_discussion"
    return "feature_or_fix_pr"


def _surface_shape_for_corpus_text(text: str) -> str:
    raw_lines = [ln.rstrip() for ln in str(text).splitlines()]
    lines = [ln.strip() for ln in raw_lines if ln.strip()]
    first = lines[0] if lines else ""
    if re.search(r"(?m)^\s*[-*]\s+", text):
        return "bullet_body"
    if re.search(r"(?m)^\s*#{1,4}\s+", text) or re.search(r"(?i)\b(summary|description|test plan|steps to reproduce|expected behavior|actual behavior)\s*:", text):
        return "sectioned_body"
    if len(lines) >= 3:
        return "multi_paragraph_body"
    if first and len(first.split()) <= 10 and len(lines) >= 2:
        return "short_subject_plus_body"
    if len(text.split()) <= 16:
        return "terse_subject"
    return "compact_paragraph"


def _length_bucket_for_word_count(word_count: int) -> str:
    if word_count < 12:
        return "000-011"
    if word_count < 32:
        return "012-031"
    if word_count < 80:
        return "032-079"
    if word_count < 160:
        return "080-159"
    return "160+"


def build_independent_semantic_style_profile(
    corpus_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    max_rows: int = 250000,
) -> Dict[str, Any]:
    """Build aggregate PR/Issue style profile from the independent corpus.

    The resulting file contains only counts and coarse buckets, never corpus
    snippets. It is safe to pass to the generator because it cannot memorize or
    reproduce evaluation benign traces; it just corrects the generator's prior
    from "generic LLM prose" toward the independent GitHub corpus mixture.
    """
    artifact_counts: Counter[str] = Counter()
    category_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    surface_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    length_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    category_surface_counts: Dict[str, Dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    category_length_counts: Dict[str, Dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))

    rows_seen = 0
    token_re = re.compile(r"[A-Za-z][A-Za-z0-9._-]{1,31}")
    token_counts_by_category: Dict[str, Counter[str]] = defaultdict(Counter)
    global_token_counts: Counter[str] = Counter()

    for row in _corpus_rows(corpus_path):
        rows_seen += 1
        if rows_seen > max_rows:
            break
        artifact_type = _artifact_type_from_corpus_row(row)
        if artifact_type not in {"PullRequest", "Issue"}:
            continue
        text = _extract_semantic_text(row)
        if not text or len(text.split()) < 4:
            continue

        category = _classify_corpus_text_style(text, artifact_type)
        surface = _surface_shape_for_corpus_text(text)
        length_bucket = _length_bucket_for_word_count(len(text.split()))
        artifact_counts[artifact_type] += 1
        category_counts[artifact_type][category] += 1
        surface_counts[artifact_type][surface] += 1
        length_counts[artifact_type][length_bucket] += 1
        category_surface_counts[artifact_type][category][surface] += 1
        category_length_counts[artifact_type][category][length_bucket] += 1

        # Aggregate token anchors are single tokens from the independent corpus,
        # not examples. Shape-only filtering prevents raw source artifacts.
        for raw in token_re.findall(text):
            low = raw.strip("._-").lower()
            if _shape_ok_for_bin_token(low):
                token_counts_by_category[f"{artifact_type}:{category}"][low] += 1
                global_token_counts[low] += 1

    if not artifact_counts:
        raise RuntimeError(f"No PullRequest/Issue style rows found in independent corpus: {corpus_path}")

    def weighted_list(counter: Counter[str], *, top: Optional[int] = None) -> List[Dict[str, Any]]:
        items = counter.most_common(top)
        return [{"label": str(label), "weight": int(weight)} for label, weight in items if weight > 0]

    artifact_profiles: Dict[str, Any] = {}
    for artifact_type in sorted(artifact_counts):
        categories = weighted_list(category_counts[artifact_type])
        cat_profiles: Dict[str, Any] = {}
        for item in categories:
            category = item["label"]
            token_key = f"{artifact_type}:{category}"
            # Choose anchors by category distinctiveness, not raw frequency,
            # so generic function words do not become another generator
            # fingerprint. This is a statistical ranking over the independent
            # corpus; it is not a whitelist or trace-derived vocabulary.
            cat_counter = token_counts_by_category[token_key]
            scored_tokens = []
            cat_total = sum(cat_counter.values()) or 1
            global_total = sum(global_token_counts.values()) or 1
            for tok, count in cat_counter.items():
                if count < 3:
                    continue
                p_cat = count / cat_total
                p_global = global_token_counts[tok] / global_total
                score = p_cat / max(p_global, 1e-9)
                scored_tokens.append((score, count, tok))
            scored_tokens.sort(reverse=True)
            cat_profiles[category] = {
                "surfaces": weighted_list(category_surface_counts[artifact_type][category]),
                "length_buckets": weighted_list(category_length_counts[artifact_type][category]),
                "anchors": [tok for _score, _count, tok in scored_tokens[:80]],
            }
        artifact_profiles[artifact_type] = {
            "rows": int(artifact_counts[artifact_type]),
            "categories": categories,
            "surfaces": weighted_list(surface_counts[artifact_type]),
            "length_buckets": weighted_list(length_counts[artifact_type]),
            "category_profiles": cat_profiles,
        }

    profile = {
        "schema": "external_github_corpus_semantic_style_profile_v1",
        "source": "independent weekly GitHub semantic corpus aggregate counts only; no evaluation trace text",
        "corpus_path": str(corpus_path),
        "rows_scanned": int(min(rows_seen, max_rows)),
        "artifact_profiles": artifact_profiles,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(profile, indent=2)[:12000], encoding="utf-8")
    print("Built independent semantic style profile:", json.dumps(profile, indent=2)[:3000])
    return profile


def _shape_ok_for_bin_token(token: str) -> bool:
    """Shape filter for corpus-derived bin tokens, not a semantic whitelist.

    The corpus parser provides candidate GitHub text; this filter removes only
    obvious non-word/source artifacts (URLs, hashes, version strings, emails,
    long path fragments) that would create visible source leakage in covert text.
    """
    if not token:
        return False
    if len(token) < 3 or len(token) > 28:
        return False
    low = token.lower().strip("._-")
    if not low:
        return False
    if low.startswith(("http", "www", "github.com", "git@")) or "@" in low:
        return False
    if "/" in low or "\\" in low:
        return False
    if re.fullmatch(r"v?\d+(?:[._-]\d+){1,}.*", low):
        return False
    if re.fullmatch(r"[a-f0-9]{8,}", low):
        return False
    if sum(ch.isdigit() for ch in low) > max(2, len(low) // 3):
        return False
    if not re.search(r"[aeiouy]", low) and len(low) > 5:
        return False
    return True


def build_calibrated_token_bins(
    corpus_path: Path,
    secrets_dir: Path,
    output_path: Path,
    report_path: Path,
    *,
    seed: int = 42,
    bin_count: int = 8,
    bin_size: int = 256,
) -> Dict[str, Any]:
    """Build semantic token bins from the independent weekly GitHub corpus.

    The bin vocabulary must not come from evaluation benign traces. We use the
    corpus/parser output that was built from GitHub semantic text for the chosen
    week, then align token-bin byte indexes to aggregate payload-byte frequency.
    No corpus snippets, benign snippets, or generated examples are sent to the
    LLM prompt; only the local codebook is changed.
    """
    token_re = re.compile(r"[A-Za-z][A-Za-z0-9._-]{1,31}")
    doc_freq: Counter[str] = Counter()
    total_freq: Counter[str] = Counter()
    casing: Dict[str, str] = {}
    doc_count = 0

    # valid_words.json/candidates.json from corpus_parser can be a JSON array of strings.
    array_words_mode = corpus_path.name in {"valid_words.json", "candidates.json"}
    for row in _corpus_rows(corpus_path):
        text = _extract_semantic_text(row)
        if not text:
            continue
        toks: List[str] = []
        for raw in token_re.findall(text):
            tok = raw.strip("._-")
            low = tok.lower()
            if not _shape_ok_for_bin_token(low):
                continue
            toks.append(low)
            casing.setdefault(low, tok if not tok.isupper() else low)
        if toks:
            doc_count += 1
            doc_freq.update(set(toks))
            total_freq.update(toks)

    if not total_freq:
        raise RuntimeError(f"No usable semantic corpus tokens found in {corpus_path}")

    min_df = 1 if array_words_mode else max(3, int(0.0005 * max(1, doc_count)))
    ranked = [w for w, df in doc_freq.items() if df >= min_df]
    if len(ranked) < bin_size:
        ranked = [w for w, _ in total_freq.most_common(max(bin_size, len(total_freq)))]
    ranked.sort(key=lambda w: (doc_freq[w], total_freq[w]), reverse=True)
    candidates = ranked[: max(bin_size * 16, bin_size)]
    if len(candidates) < bin_size:
        raise RuntimeError(
            f"Not enough independent corpus tokens for semantic bins: {len(candidates)} from {corpus_path}"
        )

    byte_counts = [1.0] * 256
    for spath in sorted(Path(secrets_dir).glob("*.txt")):
        try:
            payload = spath.read_bytes()
        except Exception:
            continue
        for bval in payload:
            byte_counts[bval] += 1.0
    ascii_prior = b" etaoinshrdlucmfwypvbgkqjxzETAOINSHRDLUCMFWYPVBGKQJXZ0123456789_-.#/:,()[]{}\n"
    for bval in ascii_prior:
        byte_counts[bval] += 2.0
    byte_order = sorted(range(min(256, bin_size)), key=lambda i: (-byte_counts[i], i))

    rng = random.Random(seed)
    weights = [max(1.0, float(doc_freq[w]) ** 0.55) for w in candidates]
    bins: List[List[str]] = []
    for _ in range(bin_count):
        pool = list(candidates)
        pool_weights = list(weights)
        chosen: List[str] = []
        for _j in range(bin_size):
            total = sum(pool_weights)
            pick = rng.random() * total
            acc = 0.0
            idx = 0
            for i, weight in enumerate(pool_weights):
                acc += weight
                if acc >= pick:
                    idx = i
                    break
            chosen.append(pool.pop(idx))
            pool_weights.pop(idx)
        chosen.sort(key=lambda w: (doc_freq[w], total_freq[w], rng.random()), reverse=True)
        ordered: List[Optional[str]] = [None] * bin_size
        for token, byte_idx in zip(chosen, byte_order):
            ordered[byte_idx] = casing.get(token, token)
        remaining = iter(casing.get(token, token) for token in chosen[len(byte_order):])
        for i in range(bin_size):
            if ordered[i] is None:
                ordered[i] = next(remaining)
        bins.append([str(x) for x in ordered])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "external_github_corpus_token_bins_v1_byte_frequency_aligned",
        "seed": seed,
        "source": "independent weekly GitHub semantic corpus plus payload byte marginals; no evaluation trace vocabulary",
        "corpus_path": str(corpus_path),
        "doc_count": doc_count,
        "bin_count": bin_count,
        "bin_size": bin_size,
        "candidate_count": len(candidates),
        "min_df": min_df,
        "bins": bins,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report = {k: v for k, v in payload.items() if k != "bins"}
    report["top_corpus_tokens"] = ranked[:50]
    report["top_payload_bytes"] = [
        {"byte": i, "char": chr(i) if 32 <= i <= 126 else "", "count": byte_counts[i]}
        for i in sorted(range(256), key=lambda b: (-byte_counts[b], b))[:32]
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Calibrated semantic token bins from independent corpus:", json.dumps(report, indent=2)[:3000])
    return report


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


def comparable_pr_issue_edit_texts(trace_dir: Path, limit: Optional[int] = None) -> List[str]:
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
                if limit is not None and len(texts) >= limit:
                    return texts
    return texts


def comparable_pr_issue_edit_records(trace_dir: Path, max_per_file: Optional[int] = 3) -> List[Dict[str, str]]:
    """File-balanced, deduped version of comparable PR/Issue edit text.

    The source diagnostic should not be dominated by one large trace file or by
    repeated PR-body duplicates. This keeps the smoke focused on semantic style
    rather than sampling artifacts.
    """
    from scripts.adversarial_evaluation import normalize_semantic_text_for_detection

    keys = ("semantic_text", "text", "body", "message", "content", "title")
    records: List[Dict[str, str]] = []
    for path in sorted(trace_dir.glob("*.jsonl")):
        file_records: List[Dict[str, str]] = []
        seen_in_file = set()
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
                action_raw = obj.get("action") or obj.get("action_type") or obj.get("actionType") or obj.get("event_type")
                action = str(action_raw).strip().lower() if action_raw else "edit"
                if action != "edit":
                    continue
                raw_text = ""
                for key in keys:
                    value = obj.get(key)
                    if value is not None and str(value).strip():
                        raw_text = str(value)
                        break
                text = normalize_semantic_text_for_detection(raw_text)
                text = re.sub(r"<img\b[^<]*(?:>|$)", " ", text, flags=re.I)
                text = re.sub(r'\b(?:img|src|alt|width|height)\b\s*=\s*"?', " ", text, flags=re.I)
                text = re.sub(r"\s+", " ", text).strip()
                if not text or len(text.split()) < 4:
                    continue
                dedupe_key = re.sub(r"\W+", " ", text.lower()).strip()
                if dedupe_key in seen_in_file:
                    continue
                seen_in_file.add(dedupe_key)
                file_records.append({"text": text, "source_file": str(path)})
                if max_per_file is not None and len(file_records) >= max_per_file:
                    break
        records.extend(file_records)

    global_seen = set()
    deduped: List[Dict[str, str]] = []
    for rec in records:
        key = re.sub(r"\W+", " ", rec["text"].lower()).strip()
        if key in global_seen:
            continue
        global_seen.add(key)
        deduped.append(rec)
    return deduped


def _length_bin(text: str) -> str:
    wc = len(text.split())
    if wc < 12:
        return "000-011"
    if wc < 32:
        return "012-031"
    if wc < 80:
        return "032-079"
    if wc < 160:
        return "080-159"
    if wc < 320:
        return "160-319"
    return "320+"


def length_matched_samples(
    benign_texts: List[str],
    covert_texts: List[str],
    *,
    max_samples_per_class: int,
    seed: int,
) -> Tuple[List[str], List[str], Dict[str, Any]]:
    """Sample benign/covert texts with matched coarse word-count support.

    The source-leak smoke test should not be passed or failed because one side
    has systematically longer PR bodies. This keeps the diagnostic focused on
    lexical/style separation after explicit source-format normalization.
    """
    rng = __import__("random").Random(seed)
    by_label = {
        "benign": defaultdict(list),
        "covert": defaultdict(list),
    }
    for text in benign_texts:
        by_label["benign"][_length_bin(text)].append(text)
    for text in covert_texts:
        by_label["covert"][_length_bin(text)].append(text)

    selected_benign: List[str] = []
    selected_covert: List[str] = []
    bin_counts: Dict[str, Dict[str, int]] = {}
    for bin_name in sorted(set(by_label["benign"]) | set(by_label["covert"])):
        b = by_label["benign"].get(bin_name, [])
        c = by_label["covert"].get(bin_name, [])
        rng.shuffle(b)
        rng.shuffle(c)
        k = min(len(b), len(c))
        if k <= 0:
            continue
        selected_benign.extend(b[:k])
        selected_covert.extend(c[:k])
        bin_counts[bin_name] = {
            "benign_available": len(b),
            "covert_available": len(c),
            "matched": k,
        }

    if not selected_benign:
        # Fall back to ordinary balanced sampling when the smoke set is tiny or
        # has no overlapping bins; the report records that length matching did
        # not apply.
        b = benign_texts[:]
        c = covert_texts[:]
        rng.shuffle(b)
        rng.shuffle(c)
        n = min(len(b), len(c), max_samples_per_class)
        return b[:n], c[:n], {
            "applied": False,
            "reason": "no overlapping word-count bins",
            "bins": {},
        }

    paired = list(zip(selected_benign, selected_covert))
    rng.shuffle(paired)
    if len(paired) > max_samples_per_class:
        paired = paired[:max_samples_per_class]

    benign_out = [b for b, _ in paired]
    covert_out = [c for _, c in paired]
    return benign_out, covert_out, {
        "applied": True,
        "bins": bin_counts,
        "raw_word_bins": {
            "benign": dict(Counter(_length_bin(t) for t in benign_texts)),
            "covert": dict(Counter(_length_bin(t) for t in covert_texts)),
        },
    }


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

    benign_records = comparable_pr_issue_edit_records(benign_dir, max_per_file=3)
    covert_records = comparable_pr_issue_edit_records(covert_sender_dir, max_per_file=3)
    benign_all = [rec["text"] for rec in benign_records]
    covert_all = [rec["text"] for rec in covert_records]
    benign_texts, covert_texts, length_match_report = length_matched_samples(
        benign_all,
        covert_all,
        max_samples_per_class=max_samples_per_class,
        seed=seed,
    )
    n = min(len(benign_texts), len(covert_texts), max_samples_per_class)

    report: Dict[str, Any] = {
        "mode": "tfidf_source_diagnostic",
        "support": "PullRequest/Issue edit text only",
        "normalization": "normalize_semantic_text_for_detection",
        "benign_count": len(benign_all),
        "covert_count": len(covert_all),
        "source_file_counts": {
            "benign": len({rec["source_file"] for rec in benign_records}),
            "covert": len({rec["source_file"] for rec in covert_records}),
        },
        "balanced_n_per_class": n,
        "length_matching": length_match_report,
        "auc_mean": None,
        "accuracy_mean": None,
        "runs": [],
        "top_tfidf_terms": {"benign": [], "covert": []},
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
        if rep == 0:
            vectorizer = clf.named_steps["tfidfvectorizer"]
            classifier = clf.named_steps["logisticregression"]
            terms = vectorizer.get_feature_names_out()
            coef = classifier.coef_[0]
            top_k = min(25, len(terms))
            covert_idx = coef.argsort()[-top_k:][::-1]
            benign_idx = coef.argsort()[:top_k]
            report["top_tfidf_terms"] = {
                "benign": [
                    {"term": str(terms[i]), "coef": float(coef[i])}
                    for i in benign_idx
                ],
                "covert": [
                    {"term": str(terms[i]), "coef": float(coef[i])}
                    for i in covert_idx
                ],
            }
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
    parser.add_argument("--smoke-only", action="store_true", help="Run only smoke generation and semantic/token reliability gates, then exit before full generation.")
    parser.add_argument("--skip-ablation", action="store_true")
    parser.add_argument("--bert-epochs", type=int, default=3)
    parser.add_argument("--bert-max-samples", type=int, default=10000)
    parser.add_argument("--skip-semantic-smoke-gate", action="store_true")
    parser.add_argument("--semantic-smoke-max-auc", type=float, default=0.98)
    parser.add_argument("--semantic-smoke-max-accuracy", type=float, default=0.95)
    parser.add_argument("--smoke-min-verification-rate", type=float, default=0.95)
    parser.add_argument("--smoke-min-successful-traces", type=int, default=20)
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

    corpus_path = find_external_semantic_corpus(root)
    build_calibrated_token_bins(
        corpus_path,
        root / "secrets",
        root / "token_binning_data" / "bins_k16.json",
        out / "calibrated_token_bins_report.json",
        seed=42,
    )
    style_profile_path = root / "token_binning_data" / "semantic_style_profile.json"
    build_independent_semantic_style_profile(
        corpus_path,
        style_profile_path,
        out / "semantic_style_profile_report.json",
    )
    os.environ["STEGO_SEMANTIC_STYLE_PROFILE"] = str(style_profile_path)

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
        smoke_rate = float(smoke_summary.get("verification_metrics", {}).get("verification_success_rate") or 0.0)
        smoke_sender_count = count_files(smoke_dir / "sender", "*.jsonl")

        # Always run the semantic/source-leak smoke diagnostics on whatever
        # smoke traces were produced. Token-binning reliability is still a
        # validity gate before the full experiment, but it should not prevent
        # the source-leak diagnostic from being written.
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

        if smoke_rate < args.smoke_min_verification_rate or smoke_sender_count < args.smoke_min_successful_traces:
            raise SystemExit(
                "Smoke generation failed token-binning verification coverage; not starting full run. "
                f"success_rate={smoke_rate:.3f}, sender_traces={smoke_sender_count}, "
                f"required_rate={args.smoke_min_verification_rate:.3f}, "
                f"required_traces={args.smoke_min_successful_traces}"
            )

        if args.smoke_only:
            print("SMOKE_ONLY_DONE. Smoke passed configured gates; full generation was not started.")
            return

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
            "--user-key", "role",
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
