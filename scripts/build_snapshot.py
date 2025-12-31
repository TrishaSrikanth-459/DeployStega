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

    HARD INVARIANTS:
    - All identifiers are real and addressable
    - No placeholder values
    - No inferred paths or branches
    - Snapshot is namespace-accurate
    """

    artifacts: Dict[str, List[Dict[str, Any]]] = {
        cls.name: [] for cls in ArtifactClass
    }

    # --------------------------------------------------------------
    # Repository
    # --------------------------------------------------------------

    artifacts["Repository"].append({
        "identifierTuple": {
            "owner": owner,
            "repo": repo,
        }
    })

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

        artifacts["Issue"].append({
            "identifierTuple": {
                "owner": owner,
                "repo": repo,
                "issue_number": issue_number,
            }
        })

        comments = paginated_get(issue["comments_url"])
        if comments:
            artifacts["IssueComment"].append({
                "identifierTuple": {
                    "owner": owner,
                    "repo": repo,
                    "issue_number": issue_number,
                }
            })

    # --------------------------------------------------------------
    # Pull Requests + PullRequestComments
    # --------------------------------------------------------------

    prs = paginated_get(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls?state=all"
    )

    for pr in prs:
        pull_number = pr["number"]
        base = pr["base"]["ref"]
        head = pr["head"]["ref"]

        artifacts["PullRequest"].append({
            "identifierTuple": {
                "owner": owner,
                "repo": repo,
                "pull_number": pull_number,
                "branch_1": base,
                "branch_2": head,
            }
        })

        comments = paginated_get(pr["_links"]["comments"]["href"])
        if comments:
            artifacts["PullRequestComment"].append({
                "identifierTuple": {
                    "owner": owner,
                    "repo": repo,
                    "pull_number": pull_number,
                }
            })

    # --------------------------------------------------------------
    # Commits + CommitComments (SAFE & ADDRESSABLE)
    # --------------------------------------------------------------

    branches = paginated_get(
        f"{GITHUB_API}/repos/{owner}/{repo}/branches"
    )

    for branch_obj in branches:
        branch = branch_obj["name"]
        commit_sha = branch_obj["commit"]["sha"]

        # Resolve commit → tree SHA
        commit_data = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/commits/{commit_sha}",
            headers=_auth_headers(),
        ).json()

        tree_sha = commit_data["tree"]["sha"]

        tree = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{tree_sha}",
            headers=_auth_headers(),
            params={"recursive": 1},
        ).json()

        paths = [
            t["path"]
            for t in tree.get("tree", [])
            if t.get("type") == "blob"
        ]

        # Bound enumeration to small, real subset
        for path in paths[:5]:
            artifacts["Commit"].append({
                "identifierTuple": {
                    "owner": owner,
                    "repo": repo,
                    "branch": branch,
                    "path": path,
                    "commit_sha": commit_sha,
                }
            })

        comments = paginated_get(
            f"{GITHUB_API}/repos/{owner}/{repo}/commits/{commit_sha}/comments"
        )

        if comments:
            artifacts["CommitComment"].append({
                "identifierTuple": {
                    "owner": owner,
                    "repo": repo,
                    "commit_sha": commit_sha,
                }
            })

    # --------------------------------------------------------------
    # HARD FILTER: drop empty classes
    # --------------------------------------------------------------

    artifacts = {
        k: v for k, v in artifacts.items() if v
    }

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
