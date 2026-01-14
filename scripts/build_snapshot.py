"""
build_snapshot.py

Authoritative experiment initializer for DeployStega.

This script is the ONLY entrypoint that creates an experiment.

It:
- Generates a unique experiment_id
- Generates opaque sender / receiver IDs
- Enumerates real GitHub routing artifacts
- Freezes a repository snapshot
- Writes BOTH:
    - experiments/snapshot.json
    - experiments/experiment_manifest.json

After this script runs:
- The experiment is fully defined
- All runtime code becomes read-only
- Sender / receiver synchronization is fixed

This script MUST be run exactly once per experiment.
"""

from __future__ import annotations

import json
import os
import time
import secrets
import requests
from pathlib import Path
from typing import Dict, List, Any

from routing.dead_drop_function.repository_snapshot.schema import ArtifactClass

# ============================================================
# Constants
# ============================================================

GITHUB_API = "https://api.github.com"
TOKEN_ENV = "GITHUB_TOKEN"

SNAPSHOT_PATH = Path("experiments/snapshot.json")
MANIFEST_PATH = Path("experiments/experiment_manifest.json")

MIN_EPOCH_OFFSET_SECONDS = 5 * 60  # 5 minutes

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "DeployStega-Snapshot/1.0",
}


# ============================================================
# Helpers
# ============================================================

def _auth_headers() -> Dict[str, str]:
    token = os.getenv(TOKEN_ENV)
    if not token:
        raise RuntimeError(f"Missing GitHub token: set {TOKEN_ENV}")
    h = dict(HEADERS)
    h["Authorization"] = f"Bearer {token}"
    return h


def paginated_get(url: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    page = 1
    while True:
        r = requests.get(
            url,
            headers=_auth_headers(),
            params={"per_page": 100, "page": page},
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        page += 1
    return out


def generate_id() -> str:
    return secrets.token_hex(16)


# ============================================================
# Snapshot construction
# ============================================================

def build_snapshot(owner: str, repo: str) -> Dict[str, List[Dict[str, Any]]]:
    artifacts: Dict[str, List[Dict[str, Any]]] = {}

    def add(cls: ArtifactClass, identifier: List[Any]) -> None:
        artifacts.setdefault(cls.name, []).append(
            {
                "artifactClass": cls.name,
                "identifier": identifier,
            }
        )

    add(ArtifactClass.Repository, [owner, repo])

    issues = paginated_get(f"{GITHUB_API}/repos/{owner}/{repo}/issues?state=all")
    for issue in issues:
        if "pull_request" in issue:
            continue
        n = issue["number"]
        add(ArtifactClass.Issue, [owner, repo, n])

        comments = paginated_get(issue["comments_url"])
        if comments:
            add(ArtifactClass.IssueComment, [owner, repo, n])

    prs = paginated_get(f"{GITHUB_API}/repos/{owner}/{repo}/pulls?state=all")
    for pr in prs:
        n = pr["number"]
        add(ArtifactClass.PullRequest, [owner, repo, n])

        comments = paginated_get(pr["_links"]["comments"]["href"])
        if comments:
            add(ArtifactClass.PullRequestComment, [owner, repo, n])

    commits = paginated_get(f"{GITHUB_API}/repos/{owner}/{repo}/commits")
    for c in commits:
        sha = c["sha"]
        add(ArtifactClass.Commit, [owner, repo, sha])

        comments = paginated_get(
            f"{GITHUB_API}/repos/{owner}/{repo}/commits/{sha}/comments"
        )
        if comments:
            add(ArtifactClass.CommitComment, [owner, repo, sha])

    if not artifacts:
        raise RuntimeError("Snapshot contains no routing artifacts")

    return artifacts


# ============================================================
# Entrypoint
# ============================================================

def main() -> None:
    print("\nBuilding routing snapshot...\n")

    owner = input("GitHub owner/org: ").strip()
    repo = input("Repository name: ").strip()

    now = int(time.time())

    epoch_origin = int(input("Epoch origin UNIX time: ").strip())
    if epoch_origin < now + MIN_EPOCH_OFFSET_SECONDS:
        raise RuntimeError(
            "Epoch origin must be at least 5 minutes in the future "
            "relative to build_snapshot execution."
        )

    epoch_end = int(input("Epoch end UNIX time: ").strip())
    if epoch_end <= epoch_origin + MIN_EPOCH_OFFSET_SECONDS:
        raise RuntimeError(
            "Epoch end must be at least 5 minutes after epoch origin."
        )

    artifacts = build_snapshot(owner, repo)

    experiment_id = f"deploystega-{int(time.time())}"

    snapshot = {
        "experiment_id": experiment_id,
        "built_at_unix": now,
        "artifacts": artifacts,
    }

    manifest = {
        "experiment_id": experiment_id,
        "snapshot": str(SNAPSHOT_PATH),
        "participants": {
            "sender": {"id": generate_id()},
            "receiver": {"id": generate_id()},
        },
        "epoch": {
            "origin_unix": epoch_origin,
            "end_unix": epoch_end,
            "duration_seconds": 180,
            "window_size": 20,
        },
    }

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2))
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))

    print("\n✅ Experiment initialized successfully")
    print(f"Experiment ID : {experiment_id}")
    print(f"Repository    : {owner}/{repo}")
    print(f"Snapshot      : {SNAPSHOT_PATH}")
    print(f"Manifest      : {MANIFEST_PATH}")

    print("\n🔐 Participant IDs (share privately):")
    print(f"Sender ID   : {manifest['participants']['sender']['id']}")
    print(f"Receiver ID : {manifest['participants']['receiver']['id']}")

    print("\n⚠️  Do NOT modify snapshot or manifest after this point.")
    print("⚠️  All runtime scripts now operate in read-only mode.\n")


if __name__ == "__main__":
    main()

