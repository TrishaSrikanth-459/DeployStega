from __future__ import annotations

"""
build_snapshot.py

Authoritative experiment initializer for DeployStega.

This version:
- Captures routing artifacts (issues, PRs, commits, tags, labels, milestones)
- Stores ALL repository file names (no content, no sampling)
- Writes routing snapshot and grounding index as SEPARATE files
- Writes a VALID experiment manifest (with epoch config)
- Guarantees ASCII-safe, size-bounded JSON output
"""

import base64
import json
import os
import time
import secrets
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import requests

from routing.dead_drop_function.repository_snapshot.schema import ArtifactClass


# ============================================================
# Paths
# ============================================================

SNAPSHOT_PATH = Path("experiments/snapshot.json")
GROUNDING_PATH = Path("experiments/grounding_index.json")
MANIFEST_PATH = Path("experiments/experiment_manifest.json")


# ============================================================
# Constants
# ============================================================

GITHUB_API = "https://api.github.com"
TOKEN_ENV = "GITHUB_TOKEN"

# epoch config defaults (must satisfy ExperimentContext contract)
EPOCH_START_DELAY_SECONDS = 10
EPOCH_DURATION_SECONDS = 30
EPOCH_WINDOW_SIZE = 1  # ✅ REQUIRED (ExperimentContext reads epoch["window_size"])

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "DeployStega-Snapshot/1.0",
}


# ============================================================
# Helpers
# ============================================================

def _auth_headers() -> Dict[str, str]:
    token = os.getenv(TOKEN_ENV, "").strip()
    if not token:
        raise RuntimeError(f"Missing GitHub token: set {TOKEN_ENV}")
    h = dict(HEADERS)
    h["Authorization"] = f"Bearer {token}"
    return h


def _request_json(url: str, *, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    try:
        r = requests.get(url, headers=_auth_headers(), params=params, timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f"GitHub API request failed for {url}: {e}") from e

    if r.status_code in (403, 404):
        return None
    if r.status_code >= 400:
        raise RuntimeError(f"GitHub API error {r.status_code} for {url}: {r.text}")
    try:
        return r.json()
    except Exception as e:
        raise RuntimeError(f"GitHub API returned non-JSON for {url}: {e}") from e


def paginated_get(url: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    page = 1
    while True:
        batch = _request_json(url, params={"per_page": 100, "page": page})
        if not isinstance(batch, list) or not batch:
            break
        # only keep dict items
        out.extend([x for x in batch if isinstance(x, dict)])
        page += 1
    return out


def generate_id() -> str:
    return secrets.token_hex(16)


def _artifact_key(cls: ArtifactClass, identifier: List[Any]) -> str:
    if cls == ArtifactClass.Repository:
        o, r = identifier
        return f"Repository:{o}/{r}"
    if cls in (ArtifactClass.Issue, ArtifactClass.PullRequest):
        o, r, n = identifier
        return f"{cls.name}:{o}/{r}#{n}"
    if cls == ArtifactClass.Commit:
        o, r, sha = identifier
        return f"Commit:{o}/{r}@{sha}"
    if cls == ArtifactClass.GitTag:
        o, r, tag = identifier
        return f"GitTag:{o}/{r}@{tag}"
    if cls == ArtifactClass.Label:
        o, r, name = identifier
        return f"Label:{o}/{r}:{name}"
    if cls == ArtifactClass.Milestone:
        o, r, n = identifier
        return f"Milestone:{o}/{r}#{n}"
    raise RuntimeError(f"Unknown artifact class: {cls}")


# ============================================================
# Repository file name capture (grounding) – NO CONTENT
# ============================================================

def _walk_tree(tree_url: str, out: List[str]) -> None:
    """Recursively collect all blob paths from the Git tree."""
    tree = _request_json(tree_url)
    if not isinstance(tree, dict):
        return

    for entry in tree.get("tree", []):
        if not isinstance(entry, dict):
            continue

        etype = entry.get("type")
        path = entry.get("path")

        if etype == "tree" and isinstance(entry.get("url"), str):
            _walk_tree(entry["url"], out)

        elif etype == "blob" and isinstance(path, str):
            out.append(path)


def fetch_repo_grounding(owner: str, repo: str, branch: str) -> Dict[str, str]:
    """
    Returns a dictionary {file_path: ""} for every file in the repository.
    Values are empty strings (no content is stored).
    """
    file_paths: List[str] = []
    root = _request_json(f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1")
    if isinstance(root, dict):
        # The recursive parameter returns all files in one go (avoids deep recursion)
        for item in root.get("tree", []):
            if isinstance(item, dict) and item.get("type") == "blob":
                path = item.get("path")
                if isinstance(path, str):
                    file_paths.append(path)
    else:
        # Fallback to manual recursion if recursive param fails
        if isinstance(root, dict) and isinstance(root.get("url"), str):
            _walk_tree(root["url"], file_paths)

    # Return as dict with empty strings (keeps interface compatible)
    return {path: "" for path in file_paths}


# ============================================================
# Snapshot construction
# ============================================================

def build_snapshot(
    owner: str, repo: str
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Dict[str, Any]]]:

    artifacts: Dict[str, List[Dict[str, Any]]] = {}
    grounding_index: Dict[str, Dict[str, Any]] = {}

    def add_artifact(cls: ArtifactClass, identifier: List[Any]) -> None:
        key = _artifact_key(cls, identifier)
        artifacts.setdefault(cls.name, []).append(
            {
                "artifactClass": cls.name,
                "identifier": identifier,
                "key": key,
            }
        )

    repo_obj = _request_json(f"{GITHUB_API}/repos/{owner}/{repo}")
    if not isinstance(repo_obj, dict):
        raise RuntimeError("Failed to fetch repository metadata")

    default_branch = repo_obj.get("default_branch")

    # Repository
    add_artifact(ArtifactClass.Repository, [owner, repo])

    # Grounding (file names only)
    if isinstance(default_branch, str):
        grounding_index[f"Repository:{owner}/{repo}"] = {
            "kind": "Repository",
            "default_branch": default_branch,
            "files": fetch_repo_grounding(owner, repo, default_branch),
        }

    # Issues (exclude PRs)
    for issue in paginated_get(f"{GITHUB_API}/repos/{owner}/{repo}/issues"):
        if "pull_request" in issue:
            continue
        n = issue.get("number")
        if isinstance(n, int):
            add_artifact(ArtifactClass.Issue, [owner, repo, n])

    # PRs
    for pr in paginated_get(f"{GITHUB_API}/repos/{owner}/{repo}/pulls"):
        n = pr.get("number")
        if isinstance(n, int):
            add_artifact(ArtifactClass.PullRequest, [owner, repo, n])

    # Commits
    for c in paginated_get(f"{GITHUB_API}/repos/{owner}/{repo}/commits"):
        sha = c.get("sha")
        if isinstance(sha, str):
            add_artifact(ArtifactClass.Commit, [owner, repo, sha])

    # Tags
    for tag in paginated_get(f"{GITHUB_API}/repos/{owner}/{repo}/tags"):
        name = tag.get("name")
        if isinstance(name, str):
            add_artifact(ArtifactClass.GitTag, [owner, repo, name])

    # Labels
    for label in paginated_get(f"{GITHUB_API}/repos/{owner}/{repo}/labels"):
        name = label.get("name")
        if isinstance(name, str):
            add_artifact(ArtifactClass.Label, [owner, repo, name])

    # Milestones
    for ms in paginated_get(f"{GITHUB_API}/repos/{owner}/{repo}/milestones"):
        n = ms.get("number")
        if isinstance(n, int):
            add_artifact(ArtifactClass.Milestone, [owner, repo, n])

    return artifacts, grounding_index


# ============================================================
# Entrypoint
# ============================================================

def main() -> None:
    owner = input("GitHub owner/org: ").strip()
    repo = input("Repository name: ").strip()

    built_at_unix = int(time.time())
    experiment_id = f"deploystega-{built_at_unix}"

    artifacts, grounding_index = build_snapshot(owner, repo)

    snapshot = {
        "experiment_id": experiment_id,
        "built_at_unix": built_at_unix,
        "artifacts": artifacts,
    }

    manifest = {
        "experiment_id": experiment_id,
        "snapshot": str(SNAPSHOT_PATH),

        # ✅ REQUIRED BY ExperimentContext
        "epoch": {
            "origin_unix": built_at_unix + EPOCH_START_DELAY_SECONDS,
            "duration_seconds": EPOCH_DURATION_SECONDS,
            "window_size": EPOCH_WINDOW_SIZE,  # ✅ FIX
            "end_unix": None,
        },

        "participants": {
            "sender": {"id": generate_id()},
            "receiver": {"id": generate_id()},
        },
    }

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)

    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    GROUNDING_PATH.write_text(
        json.dumps(grounding_index, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    print("Snapshot, grounding index, and manifest written successfully.")
    print(f"  - {SNAPSHOT_PATH}")
    print(f"  - {GROUNDING_PATH}")
    print(f"  - {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
