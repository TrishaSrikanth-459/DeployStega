"""
enumerators.py

Snapshot Construction Enumerators (REST API ONLY)

This module performs authenticated, REST-API-based enumeration of GitHub
repository artifacts for the sole purpose of constructing a fixed snapshot
prior to experimentation.

All enumeration occurs pre-experiment.
"""

from __future__ import annotations

import os
import time
import json
import random
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Iterable

import requests


# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

REST_BASE_URL = os.getenv("GITHUB_REST_BASE_URL", "https://api.github.com")
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


# -------------------------------------------------------------------
# Abstract Enumerator
# -------------------------------------------------------------------

class ArtifactEnumerator(ABC):
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    @abstractmethod
    def enumerate(self, owner: str, repo: str, **kwargs) -> List[Dict[str, Any]]:
        pass


# -------------------------------------------------------------------
# Enumerators
# -------------------------------------------------------------------

class RepositoryEnumerator(ArtifactEnumerator):
    def enumerate(self, owner: str, repo: str, **_) -> List[Dict[str, Any]]:
        return [{
            "artifactClass": "Repositories",
            "identifierTuple": {
                "owner": owner,
                "repo": repo,
            }
        }]


class IssueEnumerator(ArtifactEnumerator):
    def enumerate(
        self,
        owner: str,
        repo: str,
        max_pages: Optional[int] = None,
        **_,
    ) -> List[Dict[str, Any]]:
        out = []
        for issue in self.client.paginate(
            f"/repos/{owner}/{repo}/issues",
            params={"state": "all"},
            max_pages=max_pages,
        ):
            if "pull_request" in issue:
                continue

            out.append({
                "artifactClass": "Issues",
                "identifierTuple": {
                    "owner": owner,
                    "repo": repo,
                    "issue_number": issue["number"],
                }
            })
        return out


class PullRequestEnumerator(ArtifactEnumerator):
    def enumerate(
        self,
        owner: str,
        repo: str,
        max_pages: Optional[int] = None,
        **_,
    ) -> List[Dict[str, Any]]:
        out = []
        for pr in self.client.paginate(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": "all"},
            max_pages=max_pages,
        ):
            out.append({
                "artifactClass": "PullRequests",
                "identifierTuple": {
                    "owner": owner,
                    "repo": repo,
                    "pull_number": pr["number"],
                    "branch_1": pr["head"]["ref"],
                    "branch_2": pr["base"]["ref"],
                }
            })
        return out


class IssueCommentEnumerator(ArtifactEnumerator):
    def enumerate(
        self,
        owner: str,
        repo: str,
        max_pages: Optional[int] = None,
        **_,
    ) -> List[Dict[str, Any]]:
        out = []
        for comment in self.client.paginate(
            f"/repos/{owner}/{repo}/issues/comments",
            max_pages=max_pages,
        ):
            issue_url = comment["issue_url"]
            issue_number = int(issue_url.rstrip("/").split("/")[-1])

            out.append({
                "artifactClass": "IssueComments",
                "identifierTuple": {
                    "owner": owner,
                    "repo": repo,
                    "issue_number": issue_number,
                }
            })
        return out


class CommitEnumerator(ArtifactEnumerator):
    def enumerate(
        self,
        owner: str,
        repo: str,
        max_pages: Optional[int] = None,
        **_,
    ) -> List[Dict[str, Any]]:
        out = []
        for commit in self.client.paginate(
            f"/repos/{owner}/{repo}/commits",
            max_pages=max_pages,
        ):
            out.append({
                "artifactClass": "Commits",
                "identifierTuple": {
                    "owner": owner,
                    "repo": repo,
                    "branch": commit["commit"]["tree"]["sha"],
                    "path": "",
                    "commit_sha": commit["sha"],
                }
            })
        return out


class CommitCommentEnumerator(ArtifactEnumerator):
    def enumerate(
        self,
        owner: str,
        repo: str,
        max_pages: Optional[int] = None,
        **_,
    ) -> List[Dict[str, Any]]:
        out = []
        for comment in self.client.paginate(
            f"/repos/{owner}/{repo}/comments",
            max_pages=max_pages,
        ):
            out.append({
                "artifactClass": "CommitComments",
                "identifierTuple": {
                    "owner": owner,
                    "repo": repo,
                    "commit_sha": comment["commit_id"],
                }
            })
        return out


# -------------------------------------------------------------------
# Registry
# -------------------------------------------------------------------

ARTIFACT_ENUMERATOR_REGISTRY = {
    "Repositories": RepositoryEnumerator,
    "Issues": IssueEnumerator,
    "PullRequests": PullRequestEnumerator,
    "IssueComments": IssueCommentEnumerator,
    "CommitComments": CommitCommentEnumerator,
    "Commits": CommitEnumerator,
}


# -------------------------------------------------------------------
# Snapshot Builder
# -------------------------------------------------------------------

def build_snapshot(
    owner: str,
    repo: str,
    limits: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    token = os.getenv(TOKEN_ENV)
    if not token:
        raise RuntimeError(f"Set {TOKEN_ENV} with a GitHub access token")

    client = GitHubRESTClient(token)
    limits = limits or {}

    snapshot = {
        "repo": {"owner": owner, "repo": repo},
        "generated_at": int(time.time()),
        "artifacts": {},
    }

    for name, enum_cls in ARTIFACT_ENUMERATOR_REGISTRY.items():
        enum = enum_cls(client)
        snapshot["artifacts"][name] = enum.enumerate(
            owner, repo, **limits.get(name, {})
        )

    return snapshot


def write_snapshot(snapshot: Dict[str, Any], path: str) -> None:
    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2)


# -------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--owner", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--out", default="snapshot.json")
    p.add_argument("--max-pages", type=int, default=None)
    args = p.parse_args()

    limits = {}
    if args.max_pages is not None:
        for k in ARTIFACT_ENUMERATOR_REGISTRY:
            limits[k] = {"max_pages": args.max_pages}

    snap = build_snapshot(args.owner, args.repo, limits=limits)
    write_snapshot(snap, args.out)
    print(f"Snapshot written to {args.out}")
