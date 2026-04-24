#!/usr/bin/env python3

import os
import sys

if (
    os.environ.get("AZURE_OPENAI_API_KEY")
    and os.environ.get("AZURE_OPENAI_ENDPOINT")
    and os.environ.get("AZURE_OPENAI_DEPLOYMENT")
):
    print("[INFO] Using Azure OpenAI", flush=True)
else:
    print("[INFO] Azure OpenAI environment not fully configured", flush=True)

import argparse
import concurrent.futures
import json
import math
import random
import re
import tempfile
import time
import traceback
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from routing.dead_drop_function.dead_drop_resolver import DeadDropResolver
from routing.dead_drop_function.repository_snapshot.serializer import read_snapshot
from routing.dead_drop_function.trace_weighted_feasibility import (
    AllowAllFeasibilityRegion,
    TraceBasedFeasibilityRegion,
)
from routing.semantic.stego_decoder import ByteLevelStegoDecoder
from scripts.experiment_context import load_experiment_context


def load_azure_openai_config_from_env() -> Dict[str, str]:
    return {
        "api_key": os.environ.get("AZURE_OPENAI_API_KEY", ""),
        "endpoint": os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
        "deployment": os.environ.get("AZURE_OPENAI_DEPLOYMENT", ""),
        "api_version": os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    }


class Metrics:
    def __init__(self):
        self.strict = 0
        self.fallback = 0
        self.failed = 0

    def summary(self) -> Dict[str, float]:
        total = self.strict + self.fallback
        return {
            "total_events": total,
            "strict_events": self.strict,
            "fallback_events": self.fallback,
            "failed_events": self.failed,
            "fallback_rate": (self.fallback / total) if total else 0.0,
        }


def load_repo_distribution(benign_dir: str) -> Tuple[List[Tuple[str, str]], List[int]]:
    repo_counter = Counter()
    trace_files = sorted(Path(benign_dir).glob("user_*.jsonl"))

    for fpath in trace_files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if not first_line:
                    continue
                header = json.loads(first_line)
                repo = header.get("repo")
                if isinstance(repo, list) and len(repo) == 2:
                    repo_counter[(repo[0], repo[1])] += 1
        except Exception:
            continue

    if not repo_counter:
        raise RuntimeError(f"No repo distribution could be loaded from benign traces in {benign_dir}")

    repos = list(repo_counter.keys())
    weights = list(repo_counter.values())
    return repos, weights


VALID_ARTIFACT_CLASSES = {
    "Repository",
    "Issue",
    "PullRequest",
    "Commit",
    "IssueComment",
    "PullRequestReviewComment",
    "CommitComment",
    "GitTag",
    "Label",
    "Milestone",
}

PRIOR_ARTIFACT_MAP = {
    "PullRequestComment": "PullRequestReviewComment",
    "PullRequestReviewComment": "PullRequestReviewComment",
    "Commit": "Commit",
    "PullRequest": "PullRequest",
    "Issue": "Issue",
    "IssueComment": "IssueComment",
    "CommitComment": "CommitComment",
    "Repository": "Repository",
    "GitTag": "GitTag",
    "Label": "Label",
    "Milestone": "Milestone",
}


def normalize_artifact_class(artifact_class: Optional[str]) -> Optional[str]:
    if artifact_class == "PullRequestComment":
        return "PullRequestReviewComment"
    return artifact_class


def parse_github_url_to_identifier(url: str, default_branch: str = "main") -> Optional[Tuple[str, List[Any]]]:
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc != "github.com":
            return None

        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2:
            return None

        owner, repo = parts[0], parts[1]
        path = parsed.path

        if len(parts) == 2:
            return ("Repository", [owner, repo])

        if "/issues/" in path and len(parts) >= 4 and parts[2] == "issues" and parts[3].isdigit():
            return ("Issue", [owner, repo, int(parts[3])])

        if "/pull/" in path and len(parts) >= 4 and parts[2] == "pull" and parts[3].isdigit():
            if len(parts) >= 5 and parts[4] == "files":
                return ("PullRequestReviewComment", [owner, repo, int(parts[3])])
            return ("PullRequest", [owner, repo, int(parts[3])])

        if "/commit/" in path and len(parts) >= 4 and parts[2] == "commit":
            sha = parts[3]
            return ("Commit", [owner, repo, default_branch, sha])

        if "/releases/tag/" in path and len(parts) >= 5 and parts[2] == "releases" and parts[3] == "tag":
            tag = parts[4]
            return ("GitTag", [owner, repo, tag])

        if "/milestone/" in path and len(parts) >= 4 and parts[2] == "milestone" and parts[3].isdigit():
            return ("Milestone", [owner, repo, int(parts[3])])

        if len(parts) >= 3 and parts[2] == "issues" and parsed.query:
            q = urllib.parse.parse_qs(parsed.query).get("q", [""])[0]
            if 'label:"' in q:
                label_name = q.split('label:"', 1)[1].split('"', 1)[0]
                return ("Label", [owner, repo, label_name])

        return ("Repository", [owner, repo])
    except Exception:
        return None


def build_web_url(artifact_class: str, identifier: Sequence[Any]) -> str:
    owner, repo = identifier[0], identifier[1]

    if artifact_class == "Repository":
        return f"https://github.com/{owner}/{repo}"
    if artifact_class == "Issue":
        return f"https://github.com/{owner}/{repo}/issues/{identifier[2]}"
    if artifact_class == "PullRequest":
        return f"https://github.com/{owner}/{repo}/pull/{identifier[2]}"
    if artifact_class == "Commit":
        return f"https://github.com/{owner}/{repo}/commit/{identifier[3]}"
    if artifact_class == "IssueComment":
        return f"https://github.com/{owner}/{repo}/issues/{identifier[2]}"
    if artifact_class == "PullRequestReviewComment":
        return f"https://github.com/{owner}/{repo}/pull/{identifier[2]}/files"
    if artifact_class == "CommitComment":
        return f"https://github.com/{owner}/{repo}/commit/{identifier[2]}"
    if artifact_class == "GitTag":
        return f"https://github.com/{owner}/{repo}/releases/tag/{identifier[2]}"
    if artifact_class == "Label":
        encoded = urllib.parse.quote(str(identifier[2]), safe="")
        return f"https://github.com/{owner}/{repo}/issues?q=state%3Aopen%20label%3A%22{encoded}%22"
    if artifact_class == "Milestone":
        return f"https://github.com/{owner}/{repo}/milestone/{identifier[2]}"

    raise ValueError(f"Unsupported artifact class: {artifact_class}")


def artifact_key(artifact_class: str, identifier: Sequence[Any]) -> str:
    safe_ident = ",".join(str(x) for x in identifier)
    return f"{artifact_class}:{safe_ident}"


def extract_artifact_from_record(record: Dict[str, Any]) -> Optional[Tuple[str, List[Any]]]:
    artifact_class = normalize_artifact_class(record.get("artifact_class") or record.get("artifactClass"))
    identifier = record.get("identifier")

    if artifact_class in VALID_ARTIFACT_CLASSES and isinstance(identifier, list) and len(identifier) >= 2:
        return artifact_class, identifier

    url = record.get("url")
    if isinstance(url, str) and url.startswith("https://github.com/"):
        return parse_github_url_to_identifier(url)

    return None


def build_snapshot_for_repo_from_benign(
    owner: str,
    repo: str,
    benign_dir: str,
    out_path: Path,
) -> Path:
    artifacts: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)

    repo_identifier = [owner, repo]
    repo_record = {
        "artifactClass": "Repository",
        "identifier": repo_identifier,
        "key": artifact_key("Repository", repo_identifier),
    }
    artifacts["Repository"][repo_record["key"]] = repo_record

    trace_files = sorted(Path(benign_dir).glob("user_*.jsonl"))
    matched_trace_count = 0
    matched_event_count = 0

    for fpath in trace_files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if not first_line:
                    continue

                header = json.loads(first_line)
                repo_header = header.get("repo")
                if not (isinstance(repo_header, list) and len(repo_header) == 2):
                    continue
                if repo_header[0] != owner or repo_header[1] != repo:
                    continue

                matched_trace_count += 1

                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except Exception:
                        continue

                    artifact = extract_artifact_from_record(record)
                    if artifact is None:
                        continue

                    artifact_class, identifier = artifact
                    artifact_class = normalize_artifact_class(artifact_class)
                    if artifact_class not in VALID_ARTIFACT_CLASSES:
                        continue
                    if not isinstance(identifier, list) or len(identifier) < 2:
                        continue
                    if identifier[0] != owner or identifier[1] != repo:
                        continue

                    rec = {
                        "artifactClass": artifact_class,
                        "identifier": identifier,
                        "key": artifact_key(artifact_class, identifier),
                    }
                    artifacts[artifact_class][rec["key"]] = rec
                    matched_event_count += 1
        except Exception:
            continue

    snapshot_data = {
        "experiment_id": f"auto_snapshot_{owner}_{repo}",
        "built_at_unix": int(time.time()),
        "artifacts": {cls: list(items.values()) for cls, items in artifacts.items()},
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, indent=2)
    os.replace(tmp_path, out_path)

    print(
        f"Built repo snapshot for {owner}/{repo} at {out_path} "
        f"from {matched_trace_count} benign traces and {matched_event_count} events"
    )
    return out_path


def ensure_repo_snapshot(
    owner: str,
    repo: str,
    benign_dir: Optional[str],
    snapshot_cache_dir: Path,
    fallback_snapshot: Optional[str],
) -> str:
    safe_owner = re.sub(r"[^A-Za-z0-9_.-]", "_", owner)
    safe_repo = re.sub(r"[^A-Za-z0-9_.-]", "_", repo)
    repo_snapshot_path = snapshot_cache_dir / f"{safe_owner}__{safe_repo}.json"

    if repo_snapshot_path.exists():
        return str(repo_snapshot_path)

    if benign_dir:
        return str(build_snapshot_for_repo_from_benign(owner, repo, benign_dir, repo_snapshot_path))

    if fallback_snapshot:
        return fallback_snapshot

    raise RuntimeError(
        f"No benign trace directory available to build snapshot for {owner}/{repo}, "
        "and no fallback snapshot was provided."
    )


def estimate_secret_size(secret_text: str, estimated_bytes_per_chunk: int) -> Tuple[int, int]:
    secret_bytes = len(secret_text.encode("utf-8"))
    chunk_bytes = max(1, estimated_bytes_per_chunk)
    estimated_chunks = math.ceil(secret_bytes / chunk_bytes) if secret_bytes else 0
    return secret_bytes, estimated_chunks


def percentile_from_sorted(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])

    q = max(0.0, min(1.0, q))
    pos = (len(values) - 1) * q
    lower = int(math.floor(pos))
    upper = int(math.ceil(pos))
    if lower == upper:
        return float(values[lower])

    weight = pos - lower
    return float(values[lower] * (1.0 - weight) + values[upper] * weight)


def analyze_secret_corpus(
    secret_files: List[Path],
    start_idx: int,
    estimated_bytes_per_chunk: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    analyzable_records: List[Dict[str, Any]] = []
    empty_records: List[Dict[str, Any]] = []
    read_error_records: List[Dict[str, Any]] = []

    for local_idx, fpath in enumerate(secret_files):
        secret_id = f"{start_idx + local_idx:06d}"
        try:
            secret_text = fpath.read_text(encoding="utf-8").strip()
        except Exception as e:
            read_error_records.append(
                {
                    "secret_id": secret_id,
                    "secret_path": str(fpath),
                    "failure_stage": "read",
                    "error_message": str(e),
                }
            )
            continue

        if not secret_text:
            empty_records.append(
                {
                    "secret_id": secret_id,
                    "secret_path": str(fpath),
                    "reason": "empty_secret",
                }
            )
            continue

        secret_bytes, estimated_chunks = estimate_secret_size(secret_text, estimated_bytes_per_chunk)
        analyzable_records.append(
            {
                "secret_id": secret_id,
                "secret_path": str(fpath),
                "secret_text": secret_text,
                "secret_bytes": secret_bytes,
                "estimated_chunks": estimated_chunks,
            }
        )

    chunk_values = sorted(record["estimated_chunks"] for record in analyzable_records)
    byte_values = sorted(record["secret_bytes"] for record in analyzable_records)

    threshold_counts = {}
    for threshold in [8, 10, 12, 14, 16, 20, 24, 28, 32]:
        kept = sum(1 for value in chunk_values if value <= threshold)
        threshold_counts[str(threshold)] = {
            "kept": kept,
            "keep_rate": (kept / len(chunk_values)) if chunk_values else 0.0,
        }

    stats = {
        "total_selected_files": len(secret_files),
        "analyzable_nonempty_secrets": len(analyzable_records),
        "empty_secrets": len(empty_records),
        "read_errors": len(read_error_records),
        "secret_bytes": {
            "min": byte_values[0] if byte_values else 0,
            "mean": (sum(byte_values) / len(byte_values)) if byte_values else 0.0,
            "median": percentile_from_sorted(byte_values, 0.5),
            "p75": percentile_from_sorted(byte_values, 0.75),
            "p90": percentile_from_sorted(byte_values, 0.90),
            "max": byte_values[-1] if byte_values else 0,
        },
        "estimated_chunks": {
            "min": chunk_values[0] if chunk_values else 0,
            "mean": (sum(chunk_values) / len(chunk_values)) if chunk_values else 0.0,
            "median": percentile_from_sorted(chunk_values, 0.5),
            "p75": percentile_from_sorted(chunk_values, 0.75),
            "p90": percentile_from_sorted(chunk_values, 0.90),
            "max": chunk_values[-1] if chunk_values else 0,
        },
        "threshold_counts": threshold_counts,
    }

    return analyzable_records, empty_records, read_error_records, stats


def choose_auto_max_secret_chunks(
    analyzable_records: List[Dict[str, Any]],
    min_keep_rate: float,
) -> int:
    if not analyzable_records:
        return 1

    chunk_values = sorted(record["estimated_chunks"] for record in analyzable_records)
    total = len(chunk_values)
    required_kept = max(1, math.ceil(total * min_keep_rate))

    for threshold in chunk_values:
        kept = sum(1 for value in chunk_values if value <= threshold)
        if kept >= required_kept:
            return threshold

    return chunk_values[-1]


class BehavioralPriorSampler:
    def __init__(self, priors: Dict[str, Any], rng: random.Random):
        self.priors = priors
        self.rng = rng

        timing_vals = priors.get("ft_intra_user_timing", {}).get("sample_values", [])
        session_vals = priors.get("fsession_length", {}).get("sample_values", [])
        revisit_stats = priors.get("f_artifact_revisit", {}).get("revisit_rate", {}).get("statistics", {})
        freq_map = priors.get("f_event_type_frequency", {}).get("frequencies", {})
        transition_map = priors.get("faccess_transition_matrix", {}).get("matrix", {})

        self.timing_values = [float(x) for x in timing_vals if float(x) >= 1.0] or [179.0]
        self.session_values = [float(x) for x in session_vals if float(x) >= 0.0] or [1875.0]
        self.revisit_prob = float(revisit_stats.get("mean", 0.77))

        self.event_freq = {}
        for k, v in freq_map.items():
            mapped = PRIOR_ARTIFACT_MAP.get(k)
            if mapped in VALID_ARTIFACT_CLASSES:
                self.event_freq[mapped] = self.event_freq.get(mapped, 0.0) + float(v)

        if not self.event_freq:
            self.event_freq = {
                "Commit": 0.70,
                "PullRequest": 0.10,
                "IssueComment": 0.08,
                "PullRequestReviewComment": 0.06,
                "Issue": 0.05,
                "CommitComment": 0.01,
            }

        self.transitions: Dict[str, Dict[str, float]] = {}
        for src, dsts in transition_map.items():
            mapped_src = PRIOR_ARTIFACT_MAP.get(src)
            if mapped_src not in VALID_ARTIFACT_CLASSES:
                continue
            mapped_dsts: Dict[str, float] = {}
            for dst, prob in dsts.items():
                mapped_dst = PRIOR_ARTIFACT_MAP.get(dst)
                if mapped_dst in VALID_ARTIFACT_CLASSES:
                    mapped_dsts[mapped_dst] = mapped_dsts.get(mapped_dst, 0.0) + float(prob)
            if mapped_dsts:
                total = sum(mapped_dsts.values())
                if total > 0:
                    self.transitions[mapped_src] = {k: v / total for k, v in mapped_dsts.items()}

    def _weighted_choice(self, dist: Dict[str, float], allowed: Optional[Sequence[str]] = None) -> str:
        if allowed is not None:
            dist = {k: v for k, v in dist.items() if k in allowed}
        if not dist:
            return "Issue"
        keys = list(dist.keys())
        weights = list(dist.values())
        return self.rng.choices(keys, weights=weights, k=1)[0]

    def sample_initial_event_type(self, allowed_classes: Sequence[str]) -> str:
        return self._weighted_choice(self.event_freq, allowed=allowed_classes)

    def sample_next_event_type(self, previous: Optional[str], allowed_classes: Sequence[str]) -> str:
        if previous and previous in self.transitions:
            return self._weighted_choice(self.transitions[previous], allowed=allowed_classes)
        return self.sample_initial_event_type(allowed_classes)

    def sample_intra_gap(self) -> float:
        return float(self.rng.choice(self.timing_values))

    def sample_session_length(self) -> float:
        return float(self.rng.choice(self.session_values))

    def sample_inter_session_gap(self) -> float:
        high = [x for x in self.timing_values if x >= 1585.0]
        base = high if high else self.timing_values
        return float(self.rng.choice(base))

    def should_revisit_artifact(self) -> bool:
        return self.rng.random() < self.revisit_prob


def generate_sessioned_timestamps(num_events: int, start_time: float, prior: BehavioralPriorSampler) -> List[float]:
    timestamps: List[float] = []
    current = float(start_time)

    if num_events <= 0:
        return timestamps

    remaining_session_budget = prior.sample_session_length()

    for _ in range(num_events):
        gap = prior.sample_intra_gap()

        if gap > remaining_session_budget and timestamps:
            current += prior.sample_inter_session_gap()
            remaining_session_budget = prior.sample_session_length()
            gap = prior.sample_intra_gap()

        current += gap
        timestamps.append(current)
        remaining_session_budget = max(0.0, remaining_session_budget - gap)

    return timestamps


def snapshot_supported_classes(snapshot) -> List[str]:
    out = []
    for cls in snapshot.artifact_classes():
        if cls in VALID_ARTIFACT_CLASSES:
            out.append(cls)
        elif cls == "PullRequestComment":
            out.append("PullRequestReviewComment")
    return sorted(set(out))


def choose_identifier_from_snapshot(snapshot, artifact_class: str, rng: random.Random) -> Optional[List[Any]]:
    try:
        cls = artifact_class
        if cls == "PullRequestReviewComment" and "PullRequestReviewComment" not in snapshot.artifact_classes():
            if "PullRequestComment" in snapshot.artifact_classes():
                cls = "PullRequestComment"

        if cls not in snapshot.artifact_classes():
            return None

        arts = snapshot.artifacts_of(cls)
        if not arts:
            return None

        art = rng.choice(list(arts))
        return list(art.identifier)
    except Exception:
        return None


def choose_route_for_event(
    *,
    epoch: int,
    artifact_class: str,
    role: str,
    strict_feasibility,
    fallback_feasibility,
    snapshot,
    resolver,
    sender_id: str,
    receiver_id: str,
    owner: str,
    repo: str,
    route_memory: Dict[str, List[Tuple[List[Any], str]]],
    prior: BehavioralPriorSampler,
    rng: random.Random,
    metrics: Metrics,
) -> Tuple[List[Any], str, str]:
    if route_memory.get(artifact_class) and prior.should_revisit_artifact():
        ident, url = rng.choice(route_memory[artifact_class])
        return ident, url, artifact_class

    try:
        allowed_urls = strict_feasibility.get_allowed_urls(epoch=epoch, artifact_class=artifact_class, role=role)
    except Exception:
        allowed_urls = []

    valid_candidates: List[Tuple[List[Any], str]] = []
    for url in allowed_urls:
        parsed = parse_github_url_to_identifier(url)
        if parsed and parsed[0] == artifact_class:
            valid_candidates.append((parsed[1], url))

    if valid_candidates:
        metrics.strict += 1
        ident, url = rng.choice(valid_candidates)
        route_memory[artifact_class].append((ident, url))
        return ident, url, artifact_class

    try:
        allowed_urls = fallback_feasibility.get_allowed_urls(epoch=epoch, artifact_class=artifact_class, role=role)
    except Exception:
        allowed_urls = []

    valid_candidates = []
    for url in allowed_urls:
        parsed = parse_github_url_to_identifier(url)
        if parsed and parsed[0] == artifact_class:
            valid_candidates.append((parsed[1], url))

    if valid_candidates:
        metrics.fallback += 1
        ident, url = rng.choice(valid_candidates)
        route_memory[artifact_class].append((ident, url))
        return ident, url, artifact_class

    ident = choose_identifier_from_snapshot(snapshot, artifact_class, rng)
    if ident is not None:
        try:
            url = build_web_url(artifact_class, ident)
            metrics.fallback += 1
            route_memory[artifact_class].append((ident, url))
            return ident, url, artifact_class
        except Exception:
            pass

    try:
        result = resolver.resolve(epoch=epoch, sender_id=sender_id, receiver_id=receiver_id, role=role)
        fallback_artifact = result["artifactClass"]
        fallback_ident = list(result["identifier"]) if isinstance(result["identifier"], tuple) else result["identifier"]
        fallback_url = result["url"]

        if fallback_artifact == "PullRequestComment":
            fallback_artifact = "PullRequestReviewComment"

        if fallback_artifact not in VALID_ARTIFACT_CLASSES:
            fallback_artifact = "Issue"
            fallback_ident = [owner, repo, epoch + 1]
            fallback_url = build_web_url("Issue", fallback_ident)

        metrics.fallback += 1
        route_memory[fallback_artifact].append((fallback_ident, fallback_url))
        return fallback_ident, fallback_url, fallback_artifact
    except Exception:
        metrics.failed += 1
        ident = [owner, repo, epoch + 1]
        url = build_web_url("Issue", ident)
        route_memory["Issue"].append((ident, url))
        return ident, url, "Issue"


def encode_secret_message_in_worker(
    secret_message: str,
    artifact_class: str,
    action: str,
    azure_openai_config: Dict[str, str],
    positions_filename: Optional[str] = None,
) -> Tuple[List[str], Optional[str]]:
    os.environ["AZURE_OPENAI_API_KEY"] = azure_openai_config["api_key"]
    os.environ["AZURE_OPENAI_ENDPOINT"] = azure_openai_config["endpoint"]
    os.environ["AZURE_OPENAI_DEPLOYMENT"] = azure_openai_config["deployment"]
    os.environ["AZURE_OPENAI_API_VERSION"] = azure_openai_config["api_version"]

    from routing.semantic.stego_encoder import ByteLevelStegoEncoder

    context = {
        "artifact_class": artifact_class,
        "action": action,
    }

    encoder = ByteLevelStegoEncoder(quiet=False)
    chunks = encoder.encode(secret_message, context, positions_filename=positions_filename)
    return chunks, positions_filename


def verify_secret_encoding(
    original_secret: str,
    chunks: List[str],
    positions_file: str,
) -> Tuple[bool, str]:
    decoder = ByteLevelStegoDecoder()
    try:
        decoded = decoder.decode_with_positions(chunks, positions_file)
        decoded = decoded.strip()
        success = decoded == original_secret
        return success, decoded
    except Exception as e:
        print(f"    Verification error: {e}")
        return False, ""


def generate_receiver_trace(
    secret_id: str,
    output_receiver_dir: Path,
    snapshot,
    feasibility_dir: Optional[str],
    priors_path: str,
    sender_last_timestamp: float,
    sender_artifact_class: str,
    sender_identifier: List[Any],
    sender_url: str,
    owner: str,
    repo: str,
    sender_id: str,
    receiver_id: str,
    seed: int,
    prior: BehavioralPriorSampler,
) -> Optional[Path]:
    MAX_EVENTS = 100
    rng = random.Random(seed + int(secret_id) + 1000000)

    if feasibility_dir:
        strict_feasibility = TraceBasedFeasibilityRegion(feasibility_dir)
    else:
        strict_feasibility = AllowAllFeasibilityRegion()
    fallback_feasibility = AllowAllFeasibilityRegion()

    resolver = DeadDropResolver(
        snapshot=snapshot,
        feasibility_region=strict_feasibility,
        owner=owner,
        repo=repo,
    )

    supported = snapshot_supported_classes(snapshot)
    if not supported:
        supported = ["Issue", "PullRequest", "Repository", "Commit"]

    sampled_classes: List[str] = []
    prev_cls: Optional[str] = None
    for _ in range(MAX_EVENTS):
        cls = prior.sample_next_event_type(prev_cls, supported)
        sampled_classes.append(cls)
        prev_cls = cls

    inter_gap = prior.sample_inter_session_gap()
    receiver_start = sender_last_timestamp + inter_gap
    timestamps = generate_sessioned_timestamps(MAX_EVENTS, receiver_start, prior)

    insert_pos = rng.randint(0, MAX_EVENTS - 1)

    route_memory: Dict[str, List[Tuple[List[Any], str]]] = defaultdict(list)
    metrics = Metrics()
    events: List[Dict[str, Any]] = []

    for i in range(MAX_EVENTS):
        if i == insert_pos:
            routed_cls = sender_artifact_class
            identifier = sender_identifier
            url = sender_url
            action = "view"
            metrics.strict += 1
            route_memory[routed_cls].append((identifier, url))
        else:
            sampled_cls = sampled_classes[i]
            action = "view"
            identifier, url, routed_cls = choose_route_for_event(
                epoch=i,
                artifact_class=sampled_cls,
                role="receiver",
                strict_feasibility=strict_feasibility,
                fallback_feasibility=fallback_feasibility,
                snapshot=snapshot,
                resolver=resolver,
                sender_id=sender_id,
                receiver_id=receiver_id,
                owner=owner,
                repo=repo,
                route_memory=route_memory,
                prior=prior,
                rng=rng,
                metrics=metrics,
            )

        event = {
            "experiment_id": f"covert_{secret_id}",
            "epoch": i,
            "role": "receiver",
            "artifact_class": routed_cls,
            "action": action,
            "identifier": identifier,
            "url": url,
            "semantic_text": "",
            "semantic_meaning": None,
            "semantic_ref": None,
            "semantic_label": "receiver_view",
            "semantic_content_type": "TokenBinning_ExplicitTesting",
            "timestamp": timestamps[i],
        }
        events.append(event)

    out_file = output_receiver_dir / f"receiver_{secret_id}.jsonl"
    with open(out_file, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")

    return out_file


def process_one_secret(
    secret_text: str,
    secret_id: str,
    secret_path: str,
    output_sender_dir: Path,
    output_receiver_dir: Path,
    snapshot_path: str,
    feasibility_dir: Optional[str],
    priors_path: str,
    start_time: float,
    sender_id: str,
    receiver_id: str,
    azure_openai_config: Dict[str, str],
    owner: str,
    repo: str,
    seed: int,
) -> Tuple[Optional[str], Optional[str], Dict[str, float], Dict[str, Any]]:
    metrics = Metrics()
    verification_stats: Dict[str, Any] = {
        "secret_id": secret_id,
        "secret_path": secret_path,
        "original_secret": secret_text,
        "secret_bytes": len(secret_text.encode("utf-8")),
        "success": False,
        "decoded_secret": "",
        "chunks_encoded": 0,
        "failure_stage": None,
        "error_message": None,
        "repo": [owner, repo],
    }

    positions_file = None

    try:
        rng = random.Random(seed + int(secret_id))
        snapshot = read_snapshot(snapshot_path)

        if feasibility_dir:
            strict_feasibility = TraceBasedFeasibilityRegion(feasibility_dir)
        else:
            strict_feasibility = AllowAllFeasibilityRegion()
        fallback_feasibility = AllowAllFeasibilityRegion()

        resolver = DeadDropResolver(
            snapshot=snapshot,
            feasibility_region=strict_feasibility,
            owner=owner,
            repo=repo,
        )

        with open(priors_path, "r", encoding="utf-8") as f:
            priors = json.load(f)
        prior = BehavioralPriorSampler(priors, rng)

        supported = snapshot_supported_classes(snapshot)
        if not supported:
            supported = ["Issue", "PullRequest", "Repository", "Commit"]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            positions_file = tmp.name

        chunks = encode_secret_message_in_worker(
            secret_message=secret_text,
            artifact_class="Issue",
            action="view",
            azure_openai_config=azure_openai_config,
            positions_filename=positions_file,
        )[0]

        num_events = len(chunks)
        verification_stats["chunks_encoded"] = num_events

        if num_events == 0:
            verification_stats["failure_stage"] = "encode"
            verification_stats["error_message"] = "encoder returned 0 chunks"
            print(f"  Secret {secret_id}: encoder returned 0 chunks, skipping")
            return None, None, metrics.summary(), verification_stats

        MAX_EVENTS = 100
        if num_events > MAX_EVENTS:
            verification_stats["failure_stage"] = "encode"
            verification_stats["error_message"] = f"num_events {num_events} exceeds MAX_EVENTS {MAX_EVENTS}"
            print(f"  Secret {secret_id}: refusing {num_events} events > MAX_EVENTS={MAX_EVENTS}")
            return None, None, metrics.summary(), verification_stats

        success, decoded = verify_secret_encoding(secret_text, chunks, positions_file)
        verification_stats["success"] = success
        verification_stats["decoded_secret"] = decoded

        if not success:
            verification_stats["failure_stage"] = "verify"
            verification_stats["error_message"] = "decoded secret did not match original"
            print(f"  Verification FAILED for secret {secret_id} (decoded: '{decoded[:100]}...')")
            return None, None, metrics.summary(), verification_stats

        print(f"  Verification PASSED for secret {secret_id}")

        sampled_classes: List[str] = []
        prev_cls: Optional[str] = None
        for _ in range(num_events):
            cls = prior.sample_next_event_type(prev_cls, supported)
            sampled_classes.append(cls)
            prev_cls = cls

        timestamps = generate_sessioned_timestamps(num_events, start_time, prior)

        route_memory: Dict[str, List[Tuple[List[Any], str]]] = defaultdict(list)
        events: List[Dict[str, Any]] = []

        fixed_identifier = None
        fixed_url = None
        fixed_artifact_class = None

        for i, chunk in enumerate(chunks):
            action = "view"
            if "Comment" in sampled_classes[i]:
                action = "comment"
            elif sampled_classes[i] in ("Issue", "PullRequest"):
                action = "edit"

            if i == 0:
                identifier, url, routed_cls = choose_route_for_event(
                    epoch=i,
                    artifact_class=sampled_classes[i],
                    role="sender",
                    strict_feasibility=strict_feasibility,
                    fallback_feasibility=fallback_feasibility,
                    snapshot=snapshot,
                    resolver=resolver,
                    sender_id=sender_id,
                    receiver_id=receiver_id,
                    owner=owner,
                    repo=repo,
                    route_memory=route_memory,
                    prior=prior,
                    rng=rng,
                    metrics=metrics,
                )
                fixed_identifier = identifier
                fixed_url = url
                fixed_artifact_class = routed_cls
            else:
                identifier = fixed_identifier
                url = fixed_url
                routed_cls = fixed_artifact_class
                metrics.strict += 1
                route_memory[routed_cls].append((identifier, url))

            event = {
                "experiment_id": f"covert_{secret_id}",
                "epoch": i,
                "role": "sender",
                "artifact_class": routed_cls,
                "action": action,
                "identifier": identifier,
                "url": url,
                "semantic_text": chunk,
                "semantic_meaning": None,
                "semantic_ref": None,
                "semantic_label": "explicit_testing_payload",
                "semantic_content_type": "TokenBinning_ExplicitTesting",
                "timestamp": timestamps[i],
            }
            events.append(event)

        sender_out_file = output_sender_dir / f"trace_{secret_id}.jsonl"
        with open(sender_out_file, "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

        sender_last_timestamp = timestamps[-1] if timestamps else start_time
        receiver_out_file = generate_receiver_trace(
            secret_id=secret_id,
            output_receiver_dir=output_receiver_dir,
            snapshot=snapshot,
            feasibility_dir=feasibility_dir,
            priors_path=priors_path,
            sender_last_timestamp=sender_last_timestamp,
            sender_artifact_class=fixed_artifact_class,
            sender_identifier=fixed_identifier,
            sender_url=fixed_url,
            owner=owner,
            repo=repo,
            sender_id=sender_id,
            receiver_id=receiver_id,
            seed=seed,
            prior=prior,
        )

        print(f"  Generated sender {sender_out_file} ({num_events} events) | receiver {receiver_out_file}")
        return str(sender_out_file), str(receiver_out_file), metrics.summary(), verification_stats

    except Exception as e:
        verification_stats["failure_stage"] = "exception"
        verification_stats["error_message"] = str(e)
        verification_stats["traceback"] = traceback.format_exc()
        print(f"  Error processing secret {secret_id}: {e}")
        traceback.print_exc()
        return None, None, metrics.summary(), verification_stats
    finally:
        if positions_file:
            try:
                os.unlink(positions_file)
            except Exception:
                pass


def write_jsonl(path: Path, records: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Behaviorally grounded batch covert trace generator for DeployStega"
    )
    parser.add_argument("--secrets-dir", required=True, help="Directory containing one secret per .txt file")
    parser.add_argument("--output-dir", required=True, help="Parent directory for sender/ and receiver/ subfolders")
    parser.add_argument("--behavior-priors", required=True, help="Path to behavioral priors JSON")
    parser.add_argument("--feasibility-dir", type=str, default=None,
                        help="Path to benign traces directory (build feasibility from traces and repo distribution)")
    parser.add_argument("--num-traces", type=int, default=None,
                        help="Generate at most this many traces after slicing; omit to run the full experiment")
    parser.add_argument("--start-index", type=int, default=0,
                        help="Start from this secret index (0-based)")
    parser.add_argument("--end-index", type=int, default=None,
                        help="Stop before this secret index (exclusive)")
    parser.add_argument("--workers", type=int, default=1,
                        help="Number of parallel workers; start with 1 while debugging")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--start-time", type=float, default=1700000000,
                        help="Base Unix start time for the first event of each generated trace")
    parser.add_argument("--snapshot", type=str, default=None,
                        help="Optional fallback snapshot path when not using feasibility traces")
    parser.add_argument("--manifest", type=str, default="experiments/experiment_manifest.json",
                        help="Path to experiment manifest")
    parser.add_argument("--skip-existing", action="store_true", default=True,
                        help="Skip secret IDs that already have both sender and receiver traces")
    parser.add_argument("--max-secret-chunks", type=int, default=None,
                        help="Optional manual override. If omitted, script auto-selects the smallest threshold that keeps at least min-secret-keep-rate of non-empty secrets.")
    parser.add_argument("--estimated-bytes-per-chunk", type=int, default=12,
                        help="Estimated payload bytes carried per chunk for pre-filtering secrets")
    parser.add_argument("--min-secret-keep-rate", type=float, default=0.90,
                        help="Minimum fraction of non-empty secrets the auto-selected max-secret-chunks must retain")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    sender_dir = output_dir / "sender"
    receiver_dir = output_dir / "receiver"
    snapshot_cache_dir = output_dir / "_snapshot_cache"
    sender_dir.mkdir(parents=True, exist_ok=True)
    receiver_dir.mkdir(parents=True, exist_ok=True)
    snapshot_cache_dir.mkdir(parents=True, exist_ok=True)

    random.seed(args.seed)

    azure_openai_config = load_azure_openai_config_from_env()
    if not azure_openai_config["api_key"]:
        print("ERROR: AZURE_OPENAI_API_KEY environment variable not set.")
        sys.exit(1)
    if not azure_openai_config["endpoint"]:
        print("ERROR: AZURE_OPENAI_ENDPOINT environment variable not set.")
        sys.exit(1)
    if not azure_openai_config["deployment"]:
        print("ERROR: AZURE_OPENAI_DEPLOYMENT environment variable not set.")
        sys.exit(1)

    try:
        ctx = load_experiment_context(args.manifest)
        sender_id = ctx.sender_id
        receiver_id = ctx.receiver_id
        print(f"Loaded sender={sender_id}, receiver={receiver_id}")
    except Exception as e:
        print(f"Warning: could not load manifest, using dummy IDs: {e}")
        sender_id = "dummy_sender"
        receiver_id = "dummy_receiver"

    fallback_snapshot = None
    if args.snapshot:
        snapshot_path = Path(args.snapshot)
        if snapshot_path.exists():
            fallback_snapshot = str(snapshot_path)
            print(f"Using fallback snapshot at {snapshot_path}")
        else:
            print(f"Warning: fallback snapshot path {snapshot_path} does not exist; ignoring it")

    if args.feasibility_dir:
        repos, repo_weights = load_repo_distribution(args.feasibility_dir)
        print(f"Loaded repo distribution from benign traces ({len(repos)} unique repos)")
        print(f"Using trace-based feasibility from {args.feasibility_dir}")
    else:
        if not fallback_snapshot:
            print("Error: either --feasibility-dir or a valid --snapshot must be provided.")
            sys.exit(1)

        try:
            fallback_snapshot_obj = read_snapshot(fallback_snapshot)
        except Exception as e:
            print(f"Error loading fallback snapshot: {e}")
            sys.exit(1)

        owner = None
        repo = None
        for cls in fallback_snapshot_obj.artifact_classes():
            arts = fallback_snapshot_obj.artifacts_of(cls)
            if arts:
                owner, repo = arts[0].identifier[:2]
                break

        if not owner or not repo:
            raise RuntimeError("Cannot infer repository identity from fallback snapshot")

        repos = [(owner, repo)]
        repo_weights = [1]
        print(f"No benign trace dir provided; using single snapshot repo {owner}/{repo}")
        print("No feasibility directory provided; primary feasibility defaults to AllowAllFeasibilityRegion")

    secrets_dir = Path(args.secrets_dir)
    secret_files = sorted(secrets_dir.glob("*.txt"))
    if not secret_files:
        print(f"No .txt files found in {secrets_dir}")
        return

    total_available = len(secret_files)
    start_idx = args.start_index
    end_idx = args.end_index if args.end_index is not None else total_available

    if start_idx < 0 or start_idx >= total_available:
        print(f"Error: start-index {start_idx} out of range (0..{total_available - 1})")
        sys.exit(1)

    end_idx = min(end_idx, total_available)
    if end_idx <= start_idx:
        print(f"Error: end-index {end_idx} must be > start-index {start_idx}")
        sys.exit(1)

    secret_files = secret_files[start_idx:end_idx]
    if args.num_traces is not None and args.num_traces < len(secret_files):
        secret_files = secret_files[:args.num_traces]

    print(f"Found {total_available} secrets total")
    print(f"Selected {len(secret_files)} secrets after slicing")
    print("=" * 60)

    analyzable_records, empty_records, read_error_records, chunk_stats = analyze_secret_corpus(
        secret_files=secret_files,
        start_idx=start_idx,
        estimated_bytes_per_chunk=args.estimated_bytes_per_chunk,
    )

    print("Secret Chunk Statistics")
    print(f"  Non-empty secrets analyzed: {chunk_stats['analyzable_nonempty_secrets']}")
    print(f"  Empty secrets: {chunk_stats['empty_secrets']}")
    print(f"  Read errors: {chunk_stats['read_errors']}")
    print(
        "  Estimated chunks: "
        f"min={chunk_stats['estimated_chunks']['min']}, "
        f"mean={chunk_stats['estimated_chunks']['mean']:.2f}, "
        f"median={chunk_stats['estimated_chunks']['median']:.2f}, "
        f"p75={chunk_stats['estimated_chunks']['p75']:.2f}, "
        f"p90={chunk_stats['estimated_chunks']['p90']:.2f}, "
        f"max={chunk_stats['estimated_chunks']['max']}"
    )
    print(
        "  Secret bytes: "
        f"min={chunk_stats['secret_bytes']['min']}, "
        f"mean={chunk_stats['secret_bytes']['mean']:.2f}, "
        f"median={chunk_stats['secret_bytes']['median']:.2f}, "
        f"p75={chunk_stats['secret_bytes']['p75']:.2f}, "
        f"p90={chunk_stats['secret_bytes']['p90']:.2f}, "
        f"max={chunk_stats['secret_bytes']['max']}"
    )

    for threshold in ["8", "10", "12", "14", "16", "20", "24", "28", "32"]:
        info = chunk_stats["threshold_counts"][threshold]
        print(f"  Keep <= {threshold} chunks: {info['kept']} secrets ({info['keep_rate']:.2%})")

    if args.max_secret_chunks is None:
        effective_max_secret_chunks = choose_auto_max_secret_chunks(
            analyzable_records=analyzable_records,
            min_keep_rate=args.min_secret_keep_rate,
        )
        print(
            f"Auto-selected max-secret-chunks={effective_max_secret_chunks} "
            f"to keep at least {args.min_secret_keep_rate:.0%} of non-empty secrets"
        )
    else:
        effective_max_secret_chunks = args.max_secret_chunks
        print(f"Using user-specified max-secret-chunks={effective_max_secret_chunks}")

    print("=" * 60)
    print(f"Generating up to {len(analyzable_records)} sender traces + {len(analyzable_records)} receiver traces")
    print("=" * 60)

    results_sender: List[str] = []
    results_receiver: List[str] = []
    successful = 0
    failed = 0
    skipped = 0
    skipped_for_length = 0
    all_metric_summaries: List[Dict[str, float]] = []
    verification_results: List[Dict[str, Any]] = []
    failed_secret_records: List[Dict[str, Any]] = list(read_error_records)
    skipped_length_records: List[Dict[str, Any]] = []
    skipped_empty_records: List[Dict[str, Any]] = list(empty_records)

    snapshot_path_cache: Dict[Tuple[str, str], str] = {}

    for record in empty_records:
        skipped += 1

    for record in read_error_records:
        failed += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {}

        for record in analyzable_records:
            secret_id = record["secret_id"]
            secret_text = record["secret_text"]
            secret_bytes = record["secret_bytes"]
            estimated_chunks = record["estimated_chunks"]
            fpath = record["secret_path"]

            sender_out_file = sender_dir / f"trace_{secret_id}.jsonl"
            receiver_out_file = receiver_dir / f"receiver_{secret_id}.jsonl"

            if args.skip_existing and sender_out_file.exists() and receiver_out_file.exists():
                print(f"Skipping {secret_id} (both sender and receiver traces already exist)")
                skipped += 1
                continue

            if estimated_chunks > effective_max_secret_chunks:
                print(
                    f"Skipping {secret_id}: estimated {estimated_chunks} chunks "
                    f"({secret_bytes} bytes) exceeds max-secret-chunks={effective_max_secret_chunks}"
                )
                skipped += 1
                skipped_for_length += 1
                skipped_length_records.append(
                    {
                        "secret_id": secret_id,
                        "secret_path": fpath,
                        "secret_bytes": secret_bytes,
                        "estimated_chunks": estimated_chunks,
                        "effective_max_secret_chunks": effective_max_secret_chunks,
                        "reason": "skipped_for_length",
                        "secret_preview": secret_text[:240],
                    }
                )
                continue

            sampled_owner, sampled_repo = random.choices(repos, weights=repo_weights, k=1)[0]

            repo_key = (sampled_owner, sampled_repo)
            if repo_key not in snapshot_path_cache:
                snapshot_path_cache[repo_key] = ensure_repo_snapshot(
                    owner=sampled_owner,
                    repo=sampled_repo,
                    benign_dir=args.feasibility_dir,
                    snapshot_cache_dir=snapshot_cache_dir,
                    fallback_snapshot=fallback_snapshot,
                )

            repo_snapshot_path = snapshot_path_cache[repo_key]

            fut = executor.submit(
                process_one_secret,
                secret_text,
                secret_id,
                fpath,
                sender_dir,
                receiver_dir,
                repo_snapshot_path,
                args.feasibility_dir,
                args.behavior_priors,
                args.start_time,
                sender_id,
                receiver_id,
                azure_openai_config,
                sampled_owner,
                sampled_repo,
                args.seed,
            )
            future_map[fut] = {
                "secret_id": secret_id,
                "secret_path": fpath,
            }

        for fut in concurrent.futures.as_completed(future_map):
            meta = future_map[fut]
            secret_id = meta["secret_id"]
            try:
                sender_path, receiver_path, metric_summary, verif_stats = fut.result()
                all_metric_summaries.append(metric_summary)
                verification_results.append(verif_stats)

                if sender_path and receiver_path:
                    successful += 1
                    results_sender.append(sender_path)
                    results_receiver.append(receiver_path)
                else:
                    failed += 1
                    failed_secret_records.append(verif_stats)
                    print(f"Failed for secret {secret_id}")
            except Exception as e:
                failed += 1
                failed_secret_records.append(
                    {
                        "secret_id": secret_id,
                        "secret_path": meta["secret_path"],
                        "failure_stage": "future_exception",
                        "error_message": str(e),
                    }
                )
                print(f"Exception for secret {secret_id}: {e}")

    total_attempted = len(verification_results)
    successful_verifications = sum(1 for v in verification_results if v.get("success", False))
    verification_rate = successful_verifications / total_attempted if total_attempted else 0.0

    strict_total = sum(m["strict_events"] for m in all_metric_summaries)
    fallback_total = sum(m["fallback_events"] for m in all_metric_summaries)
    failed_event_total = sum(m["failed_events"] for m in all_metric_summaries)
    total_routed_events = strict_total + fallback_total
    global_fallback_rate = (fallback_total / total_routed_events) if total_routed_events else 0.0

    failed_log_path = output_dir / "failed_secrets.jsonl"
    skipped_length_log_path = output_dir / "skipped_length_secrets.jsonl"
    skipped_empty_log_path = output_dir / "skipped_empty_secrets.jsonl"
    chunk_stats_path = output_dir / "secret_chunk_stats.json"

    write_jsonl(failed_log_path, failed_secret_records)
    write_jsonl(skipped_length_log_path, skipped_length_records)
    write_jsonl(skipped_empty_log_path, skipped_empty_records)
    chunk_stats_path.write_text(
        json.dumps(
            {
                "chunk_stats": chunk_stats,
                "effective_max_secret_chunks": effective_max_secret_chunks,
                "min_secret_keep_rate": args.min_secret_keep_rate,
                "estimated_bytes_per_chunk": args.estimated_bytes_per_chunk,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 60)
    print("Done")
    print(f"Successful secrets: {successful}")
    print(f"Failed secrets: {failed}")
    print(f"Skipped secrets: {skipped}")
    print(f"Skipped for length: {skipped_for_length}")
    print(f"Total traces written: {successful * 2} (sender + receiver)")
    print(f"Sender traces in: {sender_dir}")
    print(f"Receiver traces in: {receiver_dir}")
    print(f"Failed secrets log: {failed_log_path}")
    print(f"Skipped length log: {skipped_length_log_path}")
    print(f"Skipped empty log: {skipped_empty_log_path}")
    print(f"Chunk stats file: {chunk_stats_path}")
    print("\nSteganographic Verification:")
    print(f"Secrets attempted: {total_attempted}")
    print(f"Successfully decoded: {successful_verifications}")
    print(f"Verification success rate: {verification_rate:.2%}")
    if failed_secret_records:
        failed_ids = [record.get("secret_id", "unknown") for record in failed_secret_records]
        if len(failed_ids) <= 10:
            print(f"Failed secret IDs: {', '.join(failed_ids)}")
        else:
            print(f"First 10 failed secret IDs: {', '.join(failed_ids[:10])} ...")
    print(f"\nStrict events (sender only): {strict_total}")
    print(f"Fallback events (sender only): {fallback_total}")
    print(f"Failed events (sender only): {failed_event_total}")
    print(f"Global fallback rate (sender only): {global_fallback_rate:.6f}")

    summary = {
        "start_index": start_idx,
        "end_index": end_idx,
        "requested_secrets": len(secret_files),
        "successful_secrets": successful,
        "failed_secrets": failed,
        "skipped_secrets": skipped,
        "skipped_for_length": skipped_for_length,
        "total_traces": successful * 2,
        "sender_traces": successful,
        "receiver_traces": successful,
        "sender_directory": str(sender_dir),
        "receiver_directory": str(receiver_dir),
        "snapshot_cache_directory": str(snapshot_cache_dir),
        "failed_secrets_log": str(failed_log_path),
        "skipped_length_log": str(skipped_length_log_path),
        "skipped_empty_log": str(skipped_empty_log_path),
        "chunk_stats_file": str(chunk_stats_path),
        "routing_metrics": {
            "strict_events": strict_total,
            "fallback_events": fallback_total,
            "failed_events": failed_event_total,
            "global_fallback_rate": global_fallback_rate,
        },
        "verification_metrics": {
            "total_attempted_secrets": total_attempted,
            "successful_verifications": successful_verifications,
            "verification_success_rate": verification_rate,
        },
        "secret_chunk_analysis": {
            "effective_max_secret_chunks": effective_max_secret_chunks,
            "min_secret_keep_rate": args.min_secret_keep_rate,
            "estimated_bytes_per_chunk": args.estimated_bytes_per_chunk,
            "stats": chunk_stats,
        },
        "parameters": {
            "workers": args.workers,
            "seed": args.seed,
            "start_time": args.start_time,
            "snapshot": args.snapshot,
            "behavior_priors": args.behavior_priors,
            "feasibility_dir": args.feasibility_dir,
            "max_secret_chunks": args.max_secret_chunks,
            "num_traces": args.num_traces,
            "azure_openai_deployment": azure_openai_config["deployment"],
            "azure_openai_api_version": azure_openai_config["api_version"],
        },
    }

    summary_file = output_dir / "generation_summary.json"
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Summary saved to: {summary_file}")


if __name__ == "__main__":
    main()

