"""
enumerators.py

Snapshot Construction Enumerators (REST API ONLY).

All enumeration occurs pre-experiment.
Only REAL, addressable, identifier-valid artifacts are emitted.
"""

from __future__ import annotations

import os
from typing import Dict, List, Any, Optional, Iterable, Set
import requests

from schema import ArtifactClass


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
            yield from data
            page += 1


# -------------------------------------------------------------------
# Enumerators
# -------------------------------------------------------------------

class RepositoryEnumerator:
    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        return [{
            "artifactClass": ArtifactClass.Repository.name,
            "identifier": [owner, repo],
        }]


class IssueEnumerator:
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        out = []
        for issue in self.client.paginate(f"/repos/{owner}/{repo}/issues", {"state": "all"}):
            if "pull_request" in issue:
                continue
            out.append({
                "artifactClass": ArtifactClass.Issue.name,
                "identifier": [owner, repo, issue["number"]],
            })
        return out


class IssueCommentEnumerator:
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        out = []
        for issue in self.client.paginate(f"/repos/{owner}/{repo}/issues", {"state": "all"}):
            if "pull_request" in issue:
                continue
            issue_number = issue["number"]
            comments = list(
                self.client.paginate(
                    f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
                    per_page=1,
                    max_pages=1,
                )
            )
            if comments:
                out.append({
                    "artifactClass": ArtifactClass.IssueComment.name,
                    "identifier": [owner, repo, issue_number],
                })
        return out


class PullRequestEnumerator:
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        return [
            {
                "artifactClass": ArtifactClass.PullRequest.name,
                "identifier": [owner, repo, pr["number"]],
            }
            for pr in self.client.paginate(f"/repos/{owner}/{repo}/pulls", {"state": "all"})
        ]


class PullRequestCommentEnumerator:
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        out = []
        for pr in self.client.paginate(f"/repos/{owner}/{repo}/pulls", {"state": "all"}):
            n = pr["number"]
            comments = list(
                self.client.paginate(
                    f"/repos/{owner}/{repo}/pulls/{n}/comments",
                    per_page=1,
                    max_pages=1,
                )
            )
            if comments:
                out.append({
                    "artifactClass": ArtifactClass.PullRequestComment.name,
                    "identifier": [owner, repo, n],
                })
        return out


class CommitEnumerator:
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        seen: Set[str] = set()
        out = []

        for commit in self.client.paginate(f"/repos/{owner}/{repo}/commits"):
            sha = commit.get("sha")
            if not sha or sha in seen:
                continue
            seen.add(sha)
            out.append({
                "artifactClass": ArtifactClass.Commit.name,
                "identifier": [owner, repo, sha],
            })

        return out


class CommitCommentEnumerator:
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        out = []
        for commit in self.client.paginate(f"/repos/{owner}/{repo}/commits"):
            sha = commit.get("sha")
            if not sha:
                continue
            comments = list(
                self.client.paginate(
                    f"/repos/{owner}/{repo}/commits/{sha}/comments",
                    per_page=1,
                    max_pages=1,
                )
            )
            if comments:
                out.append({
                    "artifactClass": ArtifactClass.CommitComment.name,
                    "identifier": [owner, repo, sha],
                })
        return out
