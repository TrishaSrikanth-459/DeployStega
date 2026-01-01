from __future__ import annotations

import json
import os
import requests
from pathlib import Path
from typing import Dict, List, Any

from routing.dead_drop_function.repository_snapshot.schema import ArtifactClass

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

GITHUB_API = "https://api.github.com"
TOKEN_ENV = "GITHUB_TOKEN"
OUTPUT_PATH = Path("experiments/snapshot.json")

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "DeployStega-Snapshot/1.0",
}

# ------------------------------------------------------------------
# REST helpers
# ------------------------------------------------------------------

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

# ------------------------------------------------------------------
# Snapshot builder
# ------------------------------------------------------------------

def build_snapshot(owner: str, repo: str) -> Dict[str, Any]:
    """
    Build a schema-valid repository snapshot.

    HARD REQUIREMENTS:
    - Identifiers MUST match schema exactly
    - Identifiers MUST correspond to user-visible GitHub URLs
    - No creation-context fields (branches, paths, base/head)
    - Snapshot is immutable and index-only
    """

    artifacts: Dict[str, List[Dict[str, Any]]] = {
        cls.name: [] for cls in ArtifactClass
    }

    seen: Dict[str, set] = {cls.name: set() for cls in ArtifactClass}

    def _add(cls: str, identifier: List[Any]) -> None:
        key = tuple(identifier)
        if key in seen[cls]:
            return
        seen[cls].add(key)
        artifacts[cls].append({
            "artifactClass": cls,
            "identifier": identifier,
        })

    # --------------------------------------------------------------
    # Repository
    # --------------------------------------------------------------

    _add("Repository", [owner, repo])

    # --------------------------------------------------------------
    # Issues + IssueComments
    # --------------------------------------------------------------

    issues = paginated_get(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues?state=all"
    )

    for issue in issues:
        if "pull_request" in issue:
            continue

        issue_number = issue["number"]
        _add("Issue", [owner, repo, issue_number])

        comments = paginated_get(issue["comments_url"])
        if comments:
            _add("IssueComment", [owner, repo, issue_number])

    # --------------------------------------------------------------
    # Pull Requests + PullRequestComments
    # --------------------------------------------------------------

    prs = paginated_get(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls?state=all"
    )

    for pr in prs:
        pull_number = pr["number"]

        _add("PullRequest", [owner, repo, pull_number])

        comments = paginated_get(pr["_links"]["comments"]["href"])
        if comments:
            _add("PullRequestComment", [owner, repo, pull_number])

    # --------------------------------------------------------------
    # Commits + CommitComments (STRICT, SNAPSHOT-BOUND)
    # --------------------------------------------------------------

    commits = paginated_get(
        f"{GITHUB_API}/repos/{owner}/{repo}/commits"
    )

    for commit in commits:
        commit_sha = commit["sha"]

        _add("Commit", [owner, repo, commit_sha])

        comments = paginated_get(
            f"{GITHUB_API}/repos/{owner}/{repo}/commits/{commit_sha}/comments"
        )
        if comments:
            _add("CommitComment", [owner, repo, commit_sha])

    # --------------------------------------------------------------
    # HARD FILTER: drop empty classes
    # --------------------------------------------------------------

    artifacts = {k: v for k, v in artifacts.items() if v}

    if not artifacts:
        raise RuntimeError("Snapshot contains no valid artifacts")

    return {"artifacts": artifacts}

# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main() -> None:
    owner = input("GitHub owner/org: ").strip()
    repo = input("Repository name: ").strip()

    snapshot = build_snapshot(owner, repo)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(snapshot, indent=2))

    print(f"✅ Snapshot written to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()



