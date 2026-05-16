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
import math
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


def collect_trace_repositories(trace_dir: Path) -> set[str]:
    """Collect owner/repo names from trace identifiers only, never text.

    This lets the independent corpus calibration match the routing/domain
    support used by the experiment without reading evaluated benign semantic
    bodies as exemplars or bin vocabulary.
    """
    repos: set[str] = set()
    for path in sorted(trace_dir.glob("*.jsonl")):
        try:
            fh = path.open("r", encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                events = obj.get("events") if isinstance(obj, dict) and isinstance(obj.get("events"), list) else [obj]
                for event in events:
                    if not isinstance(event, dict):
                        continue
                    ident = event.get("identifier")
                    if isinstance(ident, list) and len(ident) >= 2:
                        owner = str(ident[0]).strip()
                        repo = str(ident[1]).strip()
                        if owner and repo:
                            repos.add(f"{owner}/{repo}")
    return repos


def collect_semantic_support_repositories(trace_dir: Path) -> set[str]:
    """Collect repos that actually support benign PR/Issue edit text.

    This reads only event metadata and whether a text field is present, not the
    semantic text content. It prevents corpus/bin/profile calibration from being
    dragged toward route-only or malformed repos that never appear in the benign
    semantic comparison.
    """
    repos: set[str] = set()
    for path in sorted(trace_dir.glob("*.jsonl")):
        try:
            fh = path.open("r", encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                if not isinstance(event, dict):
                    continue
                artifact_class = str(event.get("artifact_class") or event.get("artifactClass") or "")
                action = str(event.get("action") or event.get("action_type") or event.get("event_type") or "")
                if artifact_class not in {"PullRequest", "Issue"} or action != "edit":
                    continue
                if not _extract_semantic_text(event):
                    continue
                ident = event.get("identifier")
                if isinstance(ident, list) and len(ident) >= 2:
                    owner = str(ident[0]).strip()
                    repo = str(ident[1]).strip()
                    if owner and repo:
                        repos.add(f"{owner}/{repo}")
    return repos


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
    repo_filter: Optional[set[str]] = None,
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
        repo = str(row.get("repository_full_name") or "") if isinstance(row, dict) else ""
        if repo_filter and repo not in repo_filter:
            continue
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

    total_style_rows = sum(artifact_counts.values())
    min_route_filtered_style_rows = 500
    if not artifact_counts or (repo_filter and total_style_rows < min_route_filtered_style_rows):
        if repo_filter:
            print(
                "Route-repo filtered style profile had insufficient independent corpus support "
                f"({total_style_rows} rows; need at least {min_route_filtered_style_rows}); "
                "falling back to full independent corpus."
            )
            return build_independent_semantic_style_profile(
                corpus_path,
                output_path,
                report_path,
                max_rows=max_rows,
                repo_filter=None,
            )
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
        "repo_filter_size": len(repo_filter or ()),
        "artifact_profiles": artifact_profiles,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_payload = json.loads(json.dumps(profile))
    for artifact_profile in (report_payload.get("artifact_profiles") or {}).values():
        for cat_profile in (artifact_profile.get("category_profiles") or {}).values():
            anchors = cat_profile.get("anchors") or []
            cat_profile["anchors"] = anchors[:20]
    report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
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
    # Tracking/query/HTML attribute names are source-format artifacts. They can
    # enter the weekly corpus through bot-rendered Markdown/HTML and become
    # obvious covert-only lexical tells if used as bin words.
    if re.fullmatch(r"(?:utm_[a-z0-9_]+|fbclid|gclid|href|src|alt|img|url)", low):
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



def build_independent_semantic_exemplars(
    corpus_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    max_rows: int = 150000,
    max_per_class: int = 300,
    seed: int = 42,
) -> Dict[str, Any]:
    """Build few-shot style references from the independent GitHub corpus.

    These are not evaluation benign traces and are never used as carrier text.
    They only give the LLM examples of real GitHub PR/issue body surface style,
    which aggregate buckets alone failed to capture.
    """
    from scripts.adversarial_evaluation import normalize_semantic_text_for_detection

    rng = random.Random(seed)
    by_class: Dict[str, List[str]] = {"PullRequest": [], "Issue": []}
    seen = set()
    rows_scanned = 0

    for row in _corpus_rows(corpus_path):
        rows_scanned += 1
        if rows_scanned > max_rows:
            break
        artifact = _artifact_type_from_corpus_row(row)
        if artifact not in by_class:
            continue
        raw = _extract_semantic_text(row)
        if not raw:
            continue
        text = normalize_semantic_text_for_detection(raw)
        text = re.sub(r"\s+", " ", text).strip()
        words = text.split()
        if len(words) < 10 or len(words) > 180:
            continue
        # Keep exemplars as natural PR/issue bodies, not transport artifacts,
        # bot footers, sponsor cards, or raw generated/scaffold pages.
        low = text.lower()
        if any(marker in low for marker in ("created by pull[bot]", "please sponsor", "automated update", "<!--", "pull request resolved")):
            continue
        if re.search(r"https?://|github\.com/|mailto:|<img\b|\|\s*---\s*\|", text, re.I):
            continue
        key = re.sub(r"\W+", " ", low).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        by_class[artifact].append(text)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "external_github_corpus_semantic_exemplars_v1",
        "source": "independent weekly GitHub semantic corpus; no evaluation benign trace text",
        "corpus_path": str(corpus_path),
        "rows_scanned": rows_scanned,
        "max_per_class": max_per_class,
        "counts_before_sample": {k: len(v) for k, v in by_class.items()},
        "counts": {},
    }
    with output_path.open("w", encoding="utf-8") as f:
        for artifact, texts in by_class.items():
            rng.shuffle(texts)
            selected = texts[:max_per_class]
            report["counts"][artifact] = len(selected)
            for text in selected:
                f.write(json.dumps({"artifact_class": artifact, "semantic_text": text}, ensure_ascii=False) + "\n")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Built independent semantic exemplars:", json.dumps(report, indent=2)[:2000])
    return report

def build_calibrated_token_bins(
    corpus_path: Path,
    secrets_dir: Path,
    output_path: Path,
    report_path: Path,
    *,
    seed: int = 42,
    bin_count: int = 16,
    bin_size: int = 256,
    repo_filter: Optional[set[str]] = None,
) -> Dict[str, Any]:
    """Build byte bins from independent PR/Issue corpus text.

    The important fix here is not another prompt tweak; it is removing the
    lexical pressure that made covert text easy to spot. Prior bins selected the
    broadest repository tokens, which over-selected ubiquitous stop-like words
    (and/the) and category-heavy nouns (package/json/site). Forced repeatedly,
    those tokens became a covert-only signature. This version uses only the
    independent weekly GitHub corpus, restricts support to PR/Issue text, and
    chooses tokens that are:
      * broad across repositories,
      * not so ubiquitous that forcing them changes function-word rates,
      * not concentrated in one PR/Issue style category.

    Root-cause note: bins must be disjoint. Reusing the same 256-token base
    vocabulary across all k=16 bins made a small set of carrier words appear in
    nearly every covert trace. Disjoint bins preserve the same token-binning
    capacity/reliability while spreading forced words over a much wider
    independent-corpus vocabulary.
    No evaluation benign or covert trace text is read.
    """
    from scripts.adversarial_evaluation import normalize_semantic_text_for_detection

    token_re = re.compile(r"[A-Za-z][A-Za-z]{2,23}")
    doc_freq: Counter[str] = Counter()
    total_freq: Counter[str] = Counter()
    repo_sets: Dict[str, set] = defaultdict(set)
    token_category_doc_freq: Dict[str, Counter[str]] = defaultdict(Counter)
    category_doc_counts: Counter[str] = Counter()
    doc_count = 0
    repos_seen = set()

    array_words_mode = corpus_path.name in {"valid_words.json", "candidates.json"}
    for row in _corpus_rows(corpus_path):
        raw_text = _extract_semantic_text(row)
        if not raw_text:
            continue
        repo = str(row.get("repository_full_name") or "") if isinstance(row, dict) else ""
        if repo_filter and repo not in repo_filter:
            continue
        artifact = _artifact_type_from_corpus_row(row)
        # Match the actual semantic-evaluation support. Pulling in commit/log
        # vocabulary gave the codebook words that are broad on GitHub but odd in
        # PR/Issue body edits.
        if not array_words_mode and artifact not in {"PullRequest", "Issue"}:
            continue
        category = f"{artifact}:{_classify_corpus_text_style(raw_text, artifact)}"

        text = normalize_semantic_text_for_detection(raw_text)
        if not text:
            continue
        toks: List[str] = []
        for raw in token_re.findall(text):
            tok = raw.strip("._-")
            low = tok.lower()
            # Shape-only filter: remove obvious source artifacts and identifiers;
            # later statistical filters handle topic/function-word skew.
            if tok != low:
                continue
            if not low.isalpha():
                continue
            if not _shape_ok_for_bin_token(low):
                continue
            toks.append(low)
        if not toks:
            continue

        doc_count += 1
        category_doc_counts[category] += 1
        if repo:
            repos_seen.add(repo)
        unique = set(toks)
        doc_freq.update(unique)
        total_freq.update(toks)
        for tok in unique:
            token_category_doc_freq[tok][category] += 1
            if repo:
                repo_sets[tok].add(repo)

    repo_count = len(repos_seen)
    if not total_freq:
        if repo_filter:
            print("Route-repo filtered token bins had no independent corpus support; falling back to full independent corpus.")
            return build_calibrated_token_bins(
                corpus_path,
                secrets_dir,
                output_path,
                report_path,
                seed=seed,
                bin_count=bin_count,
                bin_size=bin_size,
                repo_filter=None,
            )
        raise RuntimeError(f"No usable semantic corpus tokens found in {corpus_path}")

    def normalized_entropy(counter: Counter[str]) -> float:
        total = sum(counter.values())
        if total <= 0 or len(counter) <= 1:
            return 0.0
        ent = 0.0
        for value in counter.values():
            p = value / total
            ent -= p * math.log(p)
        return ent / math.log(len(counter))

    selection_passes = []
    selected_pass = "array_words"
    min_doc_freq = 1
    min_repo_freq = 0
    required_candidate_count = bin_count * bin_size

    if array_words_mode:
        candidates = [w for w, _ in total_freq.most_common(required_candidate_count)]
    else:
        # Need enough tokens for disjoint k x 256 byte bins. These are still
        # corpus-statistical thresholds, not semantic word lists: tokens must
        # appear in multiple PR/Issue documents/repos and pass source-shape
        # filtering, but we avoid selecting only the same 256 broadest tokens.
        min_doc_freq = max(5, int(0.0001 * max(1, doc_count)))
        min_repo_freq = max(2, int(0.0002 * max(1, repo_count))) if repo_count else 0
        def collect_candidates(max_doc_ratio: float, max_category_share: float, min_categories: int, min_entropy: float) -> List[str]:
            scored = []
            for tok, df in doc_freq.items():
                rf = len(repo_sets.get(tok, ())) if repo_count else df
                if df < min_doc_freq or rf < min_repo_freq:
                    continue
                df_ratio = df / max(1, doc_count)
                # Statistical stop-word ceiling. We are not banning words by
                # identity; tokens that appear in too many PR/Issue docs become
                # bad carriers because forcing them distorts style frequencies.
                if df_ratio > max_doc_ratio:
                    continue
                cat_counter = token_category_doc_freq.get(tok, Counter())
                cat_total = sum(cat_counter.values())
                if len(cat_counter) < min_categories or cat_total <= 0:
                    continue
                category_share = max(cat_counter.values()) / cat_total
                if category_share > max_category_share:
                    continue
                ent = normalized_entropy(cat_counter)
                if ent < min_entropy:
                    continue
                # Favor broad, medium-frequency, category-balanced tokens. The
                # frequency target keeps us away from both stop words and rare
                # project nouns.
                target_ratio = 0.012
                closeness = -abs(math.log(max(df_ratio, 1e-9) / target_ratio))
                score = (
                    rf / max(1, repo_count),
                    math.log1p(df),
                    ent,
                    closeness,
                    math.log1p(total_freq[tok]),
                    tok,
                )
                scored.append(score)
            scored.sort(reverse=True)
            return [tok for *_rest, tok in scored]

        for label, max_doc_ratio, max_category_share, min_categories, min_entropy in (
            ("balanced_medium", 0.075, 0.42, 4, 0.72),
            ("balanced_relaxed", 0.110, 0.50, 3, 0.68),
            ("coverage_relaxed", 0.160, 0.62, 2, 0.60),
            ("coverage_final", 0.280, 0.85, 2, 0.45),
        ):
            cand = collect_candidates(max_doc_ratio, max_category_share, min_categories, min_entropy)
            selection_passes.append(
                {
                    "label": label,
                    "max_doc_ratio": max_doc_ratio,
                    "max_category_share": max_category_share,
                    "min_categories": min_categories,
                    "min_entropy": min_entropy,
                    "candidate_count": len(cand),
                }
            )
            if len(cand) >= required_candidate_count:
                candidates = cand[:required_candidate_count]
                selected_pass = label
                break
        else:
            # Last-resort fallback is still statistical and independent-corpus
            # based; report it loudly so it cannot be mistaken for a clean pass.
            fallback = collect_candidates(0.350, 0.92, 2, 0.35)
            candidates = fallback[:required_candidate_count]
            selected_pass = "fallback_relaxed"

    if len(candidates) < required_candidate_count:
        if repo_filter:
            print(
                f"Route-repo filtered token bins found only {len(candidates)} candidates; "
                "falling back to full independent corpus."
            )
            return build_calibrated_token_bins(
                corpus_path,
                secrets_dir,
                output_path,
                report_path,
                seed=seed,
                bin_count=bin_count,
                bin_size=bin_size,
                repo_filter=None,
            )
        raise RuntimeError(
            f"Not enough independent PR/Issue corpus tokens for disjoint balanced byte bins: "
            f"{len(candidates)} available, {required_candidate_count} required from {corpus_path}"
        )

    byte_counts = [1.0] * 256
    for spath in sorted(Path(secrets_dir).glob("*.txt")):
        try:
            payload_bytes = spath.read_bytes()
        except Exception:
            continue
        for bval in payload_bytes:
            byte_counts[bval] += 1.0

    # Put broad selected tokens at byte indices that occur most often in the
    # payload corpus, independently for each disjoint bin. This preserves
    # reliability while avoiding the old repeated-256-word lexical signature.
    byte_order = sorted(range(bin_size), key=lambda b: (-byte_counts[b], b))
    selected_tokens = candidates[:required_candidate_count]
    bins: List[List[str]] = []
    for bin_idx in range(bin_count):
        bin_tokens = selected_tokens[bin_idx * bin_size:(bin_idx + 1) * bin_size]
        ordered: List[str] = [""] * bin_size
        for byte_idx, token in zip(byte_order, bin_tokens):
            ordered[byte_idx] = token
        fill_iter = iter(bin_tokens)
        for i in range(bin_size):
            if not ordered[i]:
                ordered[i] = next(fill_iter)
        bins.append(ordered)
    base_tokens = selected_tokens[:bin_size]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "external_github_corpus_token_bins_v4_balanced_pr_issue_tokens",
        "seed": seed,
        "source": "independent weekly GitHub PR/Issue corpus; category-balanced medium-frequency tokens; no evaluation trace vocabulary",
        "corpus_path": str(corpus_path),
        "doc_count": doc_count,
        "repo_count": repo_count,
        "repo_filter_size": len(repo_filter or ()),
        "category_doc_counts": dict(category_doc_counts),
        "bin_count": bin_count,
        "bin_size": bin_size,
        "candidate_count": len(candidates),
        "required_candidate_count": required_candidate_count,
        "selected_token_count": len(selected_tokens),
        "disjoint_bins": True,
        "min_doc_freq": min_doc_freq,
        "min_repo_freq": min_repo_freq,
        "selection_passes": selection_passes,
        "selected_pass": selected_pass,
        "bins": bins,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report = {k: v for k, v in payload.items() if k != "bins"}
    report["top_corpus_tokens"] = [
        {
            "token": tok,
            "doc_freq": int(doc_freq[tok]),
            "doc_ratio": float(doc_freq[tok] / max(1, doc_count)),
            "repo_freq": int(len(repo_sets.get(tok, ()))),
            "category_entropy": float(normalized_entropy(token_category_doc_freq.get(tok, Counter()))),
            "max_category_share": float(max(token_category_doc_freq.get(tok, Counter()).values()) / max(1, sum(token_category_doc_freq.get(tok, Counter()).values()))),
            "total_freq": int(total_freq[tok]),
        }
        for tok in base_tokens[:80]
    ]
    report["top_payload_byte_mapping"] = [
        {
            "byte": int(b),
            "char": chr(b) if 32 <= b <= 126 else "",
            "count": float(byte_counts[b]),
            "tokens_by_bin": [bins[bin_idx][b] for bin_idx in range(min(bin_count, 8))],
        }
        for b in byte_order[:24]
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Calibrated balanced PR/Issue semantic token bins from independent corpus:", json.dumps(report, indent=2)[:3000])
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
                ident = obj.get("identifier")
                repo = ""
                artifact_key = artifact_class
                if isinstance(ident, list) and len(ident) >= 2:
                    repo = f"{str(ident[0]).strip()}/{str(ident[1]).strip()}"
                    artifact_key = repo + "/" + artifact_class + "/" + "/".join(str(x) for x in ident[2:])
                file_records.append({"text": text, "source_file": str(path), "repo": repo, "artifact_key": artifact_key})
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
    """Run a grouped semantic source-leak smoke test.

    Earlier smoke diagnostics split individual text rows at random. That let the
    classifier see other rows from the same trace file in train and test, so it
    could memorize trace/repo/topic quirks instead of measuring source-style
    generalization. This version keeps source files disjoint between train/test
    and length-matches within each split.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, roc_auc_score
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.pipeline import make_pipeline

    def match_records(
        benign_records_in: List[Dict[str, str]],
        covert_records_in: List[Dict[str, str]],
        rng_seed: int,
        cap: int,
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], Dict[str, Any]]:
        rng = __import__("random").Random(rng_seed)
        selected_b: List[Dict[str, str]] = []
        selected_c: List[Dict[str, str]] = []
        used_b: set[int] = set()
        used_c: set[int] = set()
        bins: Dict[str, Dict[str, int]] = {}

        def _match_on(key_fn, label_prefix: str) -> None:
            by_label = {"benign": defaultdict(list), "covert": defaultdict(list)}
            for rec in benign_records_in:
                if id(rec) not in used_b:
                    by_label["benign"][key_fn(rec)].append(rec)
            for rec in covert_records_in:
                if id(rec) not in used_c:
                    by_label["covert"][key_fn(rec)].append(rec)
            for key in sorted(set(by_label["benign"]) | set(by_label["covert"])):
                b = by_label["benign"].get(key, [])[:]
                c = by_label["covert"].get(key, [])[:]
                rng.shuffle(b)
                rng.shuffle(c)
                k = min(len(b), len(c))
                if k <= 0:
                    continue
                chosen_b = b[:k]
                chosen_c = c[:k]
                selected_b.extend(chosen_b)
                selected_c.extend(chosen_c)
                used_b.update(id(x) for x in chosen_b)
                used_c.update(id(x) for x in chosen_c)
                bins[f"{label_prefix}|{key}"] = {
                    "match_key": str(key),
                    "benign_available": len(b),
                    "covert_available": len(c),
                    "matched": k,
                }

        # Strongest control first: same public artifact identifier and length
        # bin. If a tiny smoke has too little exact support, fall back to repo +
        # length, then length-only. These are metadata controls, not text reuse.
        min_comparable = min(20, cap)
        _match_on(lambda rec: (rec.get("artifact_key", ""), _length_bin(rec["text"])), "artifact_length")
        # Exact public-artifact matching is the strongest control, but small
        # smokes often have only a handful of exact overlapping identifiers.
        # If exact matching is under-powered, fall back to repo+length so the
        # diagnostic remains statistically meaningful rather than silently
        # skipping and hiding semantic separability.
        if len(selected_b) < min_comparable:
            _match_on(lambda rec: (rec.get("repo", ""), _length_bin(rec["text"])), "repo_length")
        if len(selected_b) < min_comparable:
            _match_on(lambda rec: _length_bin(rec["text"]), "length")
        if not selected_b:
            b = benign_records_in[:]
            c = covert_records_in[:]
            rng.shuffle(b)
            rng.shuffle(c)
            n0 = min(len(b), len(c), cap)
            return b[:n0], c[:n0], {"applied": False, "reason": "no overlapping repo+word-count or word-count bins", "bins": {}}
        paired = list(zip(selected_b, selected_c))
        rng.shuffle(paired)
        if len(paired) > cap:
            paired = paired[:cap]
        return [b for b, _ in paired], [c for _, c in paired], {
            "applied": True,
            "bins": bins,
            "raw_word_bins": {
                "benign": dict(Counter(_length_bin(rec["text"]) for rec in benign_records_in)),
                "covert": dict(Counter(_length_bin(rec["text"]) for rec in covert_records_in)),
            },
        }

    # Keep enough same-artifact evidence for the smoke diagnostic. Source-file
    # grouping prevents train/test leakage, so limiting to only the first few
    # records per file can artificially erase true public-artifact overlap and
    # force noisy repo-only matching.
    benign_records = comparable_pr_issue_edit_records(benign_dir, max_per_file=25)
    covert_records = comparable_pr_issue_edit_records(covert_sender_dir, max_per_file=25)
    source_file_counts = {
        "benign": len({rec["source_file"] for rec in benign_records}),
        "covert": len({rec["source_file"] for rec in covert_records}),
    }

    b_matched, c_matched, length_match_report = match_records(
        benign_records,
        covert_records,
        rng_seed=seed,
        cap=max_samples_per_class,
    )
    n = min(len(b_matched), len(c_matched), max_samples_per_class)

    report: Dict[str, Any] = {
        "mode": "tfidf_source_diagnostic_grouped_by_source_file",
        "support": "PullRequest/Issue edit text only",
        "normalization": "normalize_semantic_text_for_detection",
        "split_policy": "GroupShuffleSplit by source_file; no trace file appears in both train and test",
        "matching_policy": "Match benign/covert records by public artifact identifier and word-count bin before TF-IDF; fallback to repo+length, then length-only if tiny smoke lacks exact overlap",
        "benign_count": len(benign_records),
        "covert_count": len(covert_records),
        "source_file_counts": source_file_counts,
        "repo_counts": {
            "benign": len({rec.get("repo", "") for rec in benign_records if rec.get("repo", "")}),
            "covert": len({rec.get("repo", "") for rec in covert_records if rec.get("repo", "")}),
            "overlap": len(
                {rec.get("repo", "") for rec in benign_records if rec.get("repo", "")}
                & {rec.get("repo", "") for rec in covert_records if rec.get("repo", "")}
            ),
        },
        "artifact_key_counts": {
            "benign": len({rec.get("artifact_key", "") for rec in benign_records if rec.get("artifact_key", "")}),
            "covert": len({rec.get("artifact_key", "") for rec in covert_records if rec.get("artifact_key", "")}),
            "overlap": len(
                {rec.get("artifact_key", "") for rec in benign_records if rec.get("artifact_key", "")}
                & {rec.get("artifact_key", "") for rec in covert_records if rec.get("artifact_key", "")}
            ),
        },
        "balanced_n_per_class": n,
        "length_matching": length_match_report,
        "auc_mean": None,
        "accuracy_mean": None,
        "runs": [],
        "top_tfidf_terms": {"benign": [], "covert": []},
        "benign_examples": [rec["text"] for rec in b_matched[:5]],
        "covert_examples": [rec["text"] for rec in c_matched[:5]],
    }

    if n < 20 or source_file_counts["covert"] < 8 or source_file_counts["benign"] < 8:
        report["skipped"] = True
        report["reason"] = "Need at least 20 comparable texts/class and >=8 source files/class for grouped smoke diagnostic."
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2)[:4000])
        return report

    records = b_matched[:n] + c_matched[:n]
    texts = [rec["text"] for rec in records]
    labels = [0] * n + [1] * n
    groups = [rec["source_file"] for rec in records]

    for rep in range(repeats):
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.35, random_state=seed + rep)
        train_idx, test_idx = next(splitter.split(texts, labels, groups))
        x_train = [texts[i] for i in train_idx]
        x_test = [texts[i] for i in test_idx]
        y_train = [labels[i] for i in train_idx]
        y_test = [labels[i] for i in test_idx]
        if len(set(y_train)) < 2 or len(set(y_test)) < 2:
            report["runs"].append({"repeat": rep, "skipped": True, "reason": "group split produced one class"})
            continue
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
        if not report["top_tfidf_terms"]["benign"]:
            vectorizer = clf.named_steps["tfidfvectorizer"]
            classifier = clf.named_steps["logisticregression"]
            terms = vectorizer.get_feature_names_out()
            coef = classifier.coef_[0]
            top_k = min(25, len(terms))
            covert_idx = coef.argsort()[-top_k:][::-1]
            benign_idx = coef.argsort()[:top_k]
            report["top_tfidf_terms"] = {
                "benign": [{"term": str(terms[i]), "coef": float(coef[i])} for i in benign_idx],
                "covert": [{"term": str(terms[i]), "coef": float(coef[i])} for i in covert_idx],
            }
        report["runs"].append({
            "repeat": rep,
            "auc": float(roc_auc_score(y_test, scores)),
            "accuracy": float(accuracy_score(y_test, preds)),
            "train_source_files": len({groups[i] for i in train_idx}),
            "test_source_files": len({groups[i] for i in test_idx}),
        })

    valid_runs = [r for r in report["runs"] if "auc" in r]
    if not valid_runs:
        report["skipped"] = True
        report["reason"] = "All grouped splits were single-class; increase smoke trace count."
    else:
        report["auc_mean"] = float(sum(r["auc"] for r in valid_runs) / len(valid_runs))
        report["accuracy_mean"] = float(sum(r["accuracy"] for r in valid_runs) / len(valid_runs))
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
    parser.add_argument("--smoke-max-secret-chunks", type=int, default=20, help="Maximum estimated chunks per smoke secret; lower values make semantic iteration faster.")
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
    parser.add_argument("--smoke-seed", type=int, default=123, help="Seed for smoke trace generation and grouped semantic diagnostic")
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
    route_repo_filter = collect_semantic_support_repositories(root / "benign_traces")
    if not route_repo_filter:
        route_repo_filter = collect_trace_repositories(root / "benign_traces")
    (out / "route_repo_filter_report.json").write_text(
        json.dumps({
            "repo_count": len(route_repo_filter),
            "source": "benign PR/Issue-edit repo identifiers and text-field presence only; no semantic text content",
        }, indent=2),
        encoding="utf-8",
    )
    token_bin_count = int(os.environ.get("DEPLOYSTEGA_TOKEN_BIN_COUNT", "16"))
    build_calibrated_token_bins(
        corpus_path,
        root / "secrets",
        root / "token_binning_data" / "bins_k16.json",
        out / "calibrated_token_bins_report.json",
        seed=42,
        bin_count=token_bin_count,
        repo_filter=route_repo_filter,
    )
    style_profile_path = root / "token_binning_data" / "semantic_style_profile.json"
    build_independent_semantic_style_profile(
        corpus_path,
        style_profile_path,
        out / "semantic_style_profile_report.json",
        repo_filter=route_repo_filter,
    )
    os.environ["STEGO_SEMANTIC_STYLE_PROFILE"] = str(style_profile_path)

    # Do not pass full corpus snippets to the LLM. The generator uses only the
    # aggregate semantic_style_profile above; keeping exemplar snippets out avoids
    # both evaluation-trace leakage and independent-corpus phrase copying.
    os.environ.pop("STEGO_BENIGN_EXEMPLARS_PATH", None)

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
            "--seed", str(args.smoke_seed),
            "--max-secret-chunks", str(args.smoke_max_secret_chunks),
            "--estimated-bytes-per-chunk", "4",
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
            seed=args.smoke_seed,
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
            "--estimated-bytes-per-chunk", "4",
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
