"""
enumerators.py

Snapshot Construction Enumerators (REST API ONLY)

All enumeration occurs pre-experiment.
Only REAL, addressable, identifier-valid artifacts are emitted.
"""

from __future__ import annotations

import os
from typing import Dict, List, Any, Optional, Iterable, Set

import requests


# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

REST_BASE_URL = "https://api.github.com"
TOKEN_ENV = "GITHUB_TOKEN"

DEFAULT_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "DeployStega-Snapshot/1.0",
}


# -------------------------------------------------------------------
# REST Client
# -------------------------------------------------------------------

class GitHubRESTClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.session.headers["Authorization"] = f"Bearer {token}"

    def paginate(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        per_page: int = 100,
        max_pages: Optional[int] = None,
    ) -> Iterable[Dict[str, Any]]:
        params = dict(params or {})
        params["per_page"] = per_page
        page = 1

        while True:
            if max_pages is not None and page > max_pages:
                return

            params["page"] = page
            resp = self.session.get(f"{REST_BASE_URL}{path}", params=params)
            resp.raise_for_status()
            data = resp.json()

            if not data:
                return

            for item in data:
                yield item

            page += 1

    def get(self, path: str) -> Dict[str, Any]:
        resp = self.session.get(f"{REST_BASE_URL}{path}")
        resp.raise_for_status()
        return resp.json()


# -------------------------------------------------------------------
# Enumerators
# -------------------------------------------------------------------

class RepositoryEnumerator:
    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        return [{
            "artifactClass": "Repository",
            "identifierTuple": {
                "owner": owner,
                "repo": repo,
            }
        }]


class IssueEnumerator:
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []

        for issue in self.client.paginate(
            f"/repos/{owner}/{repo}/issues",
            params={"state": "all"},
        ):
            if "pull_request" in issue:
                continue

            out.append({
                "artifactClass": "Issue",
                "identifierTuple": {
                    "owner": owner,
                    "repo": repo,
                    "issue_number": issue["number"],
                }
            })

        return out


class PullRequestEnumerator:
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []

        for pr in self.client.paginate(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": "all"},
        ):
            out.append({
                "artifactClass": "PullRequest",
                "identifierTuple": {
                    "owner": owner,
                    "repo": repo,
                    "pull_number": pr["number"],
                    "branch_1": pr["base"]["ref"],
                    "branch_2": pr["head"]["ref"],
                }
            })

        return out


class CommitEnumerator:
    """
    STRICT commit enumerator.

    Emits a Commit ONLY if:
    - branch is concrete
    - path is concrete
    - commit_sha is concrete
    - resulting edit/new URL is valid
    """

    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen: Set[tuple] = set()

        # Enumerate branches
        for branch_obj in self.client.paginate(
            f"/repos/{owner}/{repo}/branches"
        ):
            branch = branch_obj.get("name")
            if not branch:
                continue

            # Enumerate commits on branch
            for commit in self.client.paginate(
                f"/repos/{owner}/{repo}/commits",
                params={"sha": branch},
            ):
                commit_sha = commit.get("sha")
                if not commit_sha:
                    continue

                # Fetch full commit details (REQUIRED for files)
                try:
                    details = self.client.get(
                        f"/repos/{owner}/{repo}/commits/{commit_sha}"
                    )
                except requests.HTTPError:
                    continue

                files = details.get("files")
                if not files:
                    continue

                for f in files:
                    path = f.get("filename")
                    if not path:
                        continue

                    key = (branch, path, commit_sha)
                    if key in seen:
                        continue
                    seen.add(key)

                    out.append({
                        "artifactClass": "Commit",
                        "identifierTuple": {
                            "owner": owner,
                            "repo": repo,
                            "branch": branch,
                            "path": path,
                            "commit_sha": commit_sha,
                        }
                    })

        return out


# -------------------------------------------------------------------
# Snapshot Builder
# -------------------------------------------------------------------

def build_snapshot(owner: str, repo: str) -> Dict[str, Any]:
    token = os.getenv(TOKEN_ENV)
    if not token:
        raise RuntimeError(f"Set {TOKEN_ENV} with a GitHub access token")

    client = GitHubRESTClient(token)

    snapshot: Dict[str, Any] = {
        "artifacts": {}
    }

    snapshot["artifacts"]["Repository"] = RepositoryEnumerator().enumerate(owner, repo)
    snapshot["artifacts"]["Issue"] = IssueEnumerator(client).enumerate(owner, repo)
    snapshot["artifacts"]["PullRequest"] = PullRequestEnumerator(client).enumerate(owner, repo)
    snapshot["artifacts"]["Commit"] = CommitEnumerator(client).enumerate(owner, repo)

    # HARD FILTER: remove empty artifact classes
    snapshot["artifacts"] = {
        cls: items
        for cls, items in snapshot["artifacts"].items()
        if items
    }

    return snapshot
