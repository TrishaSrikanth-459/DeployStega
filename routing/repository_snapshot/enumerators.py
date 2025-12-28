"""
enumerators.py

Snapshot Construction Enumerators

===========================================================================
SNAPSHOT ENUMERATION SCOPE
===========================================================================

This module performs authenticated, REST-API-based enumeration of GitHub
repository artifacts for the sole purpose of constructing a fixed snapshot
prior to experimentation.

===========================================================================
USAGE
===========================================================================

Prerequisites:
  1. Create a GitHub access token with READ access to the target repository.
     - Public repo: no special scopes required
     - Private repo: token must have repository read permissions
  2. Export the token as an environment variable:

        export GITHUB_TOKEN=ghp_your_token_here

Running the snapshot enumerator:

    python enumerators.py --owner <OWNER> --repo <REPO> [--max-pages N]

Example (small public repo):

    python enumerators.py --owner octocat --repo Hello-World --max-pages 1

Example (private repo you own):

    python enumerators.py --owner your-username --repo your-private-repo --max-pages 1

Output:
  - Writes a JSON snapshot file (default: snapshot.json)
  - The snapshot contains only existing artifact identifiers
  - No API calls are made after snapshot construction completes

Notes:
  - This module is intended for pre-experiment snapshot construction only.
  - All API activity occurs before any detectability or runtime evaluation.
  - Pagination limits (--max-pages) are recommended for large repositories.
"""

from __future__ import annotations

import os
import time
import json
import random
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Iterable, Tuple

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
# REST Client with Pagination + Rate Limit Handling
# -------------------------------------------------------------------

class GitHubRESTClient:
    """
    Minimal REST client with:
      - authentication
      - pagination crawling
      - rate-limit backoff
    """

    def __init__(
        self,
        token: str,
        timeout: int = 30,
        max_retries: int = 6,
    ):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.timeout = timeout
        self.max_retries = max_retries

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        url = f"{REST_BASE_URL}{path}"
        return self._request_with_backoff("GET", url, params=params)

    def paginate(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        per_page: int = 100,
        max_pages: Optional[int] = None,
    ) -> Iterable[Dict[str, Any]]:
        """
        Crawl all REST pages for an endpoint returning an array.
        """
        params = dict(params or {})
        params["per_page"] = per_page
        page_count = 0

        url = f"{REST_BASE_URL}{path}"

        while True:
            if max_pages is not None and page_count >= max_pages:
                return

            resp = self._request_with_backoff("GET", url, params=params)
            data = resp.json()

            if not isinstance(data, list):
                return

            for item in data:
                yield item

            page_count += 1
            next_url = self._next_link(resp.headers.get("Link", ""))
            if not next_url:
                return

            url = next_url
            params = None  # already encoded in next_url

    def _request_with_backoff(self, method: str, url: str, **kwargs) -> requests.Response:
        for attempt in range(self.max_retries):
            resp = self.session.request(method, url, timeout=self.timeout, **kwargs)

            if resp.status_code == 200:
                return resp

            # Primary rate limit
            if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
                reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
                sleep_time = max(0, reset - int(time.time())) + 1
                time.sleep(sleep_time)
                continue

            # Secondary limits / transient errors
            if resp.status_code in (403, 429) or 500 <= resp.status_code < 600:
                time.sleep(min(2 ** attempt, 30) + random.random())
                continue

            raise RuntimeError(f"REST error {resp.status_code}: {resp.text[:300]}")

        raise RuntimeError("Exceeded REST retry budget")

    @staticmethod
    def _next_link(link_header: str) -> Optional[str]:
        if not link_header:
            return None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                return part[part.find("<") + 1 : part.find(">")]
        return None


# -------------------------------------------------------------------
# Abstract Enumerator
# -------------------------------------------------------------------

class ArtifactEnumerator(ABC):
    """
    Enumerators crawl REST API pages to extract artifact identifiers.
    """

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
        data = self.client.get(f"/repos/{owner}/{repo}").json()
        return [{
            "artifactClass": "Repositories",
            "identifierTuple": {
                "owner": owner,
                "repo": repo,
                "repo_id": data["id"],
                "node_id": data["node_id"],
            }
        }]


class IssueEnumerator(ArtifactEnumerator):

    def enumerate(
        self,
        owner: str,
        repo: str,
        state: str = "all",
        max_pages: Optional[int] = None,
        **_,
    ) -> List[Dict[str, Any]]:
        out = []
        for item in self.client.paginate(
            f"/repos/{owner}/{repo}/issues",
            params={"state": state},
            max_pages=max_pages,
        ):
            if "pull_request" in item:
                continue
            out.append({
                "artifactClass": "Issues",
                "identifierTuple": {
                    "owner": owner,
                    "repo": repo,
                    "number": item["number"],
                    "issue_id": item["id"],
                    "node_id": item["node_id"],
                }
            })
        return out


class PullRequestEnumerator(ArtifactEnumerator):

    def enumerate(
        self,
        owner: str,
        repo: str,
        state: str = "all",
        max_pages: Optional[int] = None,
        **_,
    ) -> List[Dict[str, Any]]:
        out = []
        for item in self.client.paginate(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": state},
            max_pages=max_pages,
        ):
            out.append({
                "artifactClass": "PullRequests",
                "identifierTuple": {
                    "owner": owner,
                    "repo": repo,
                    "number": item["number"],
                    "pr_id": item["id"],
                    "node_id": item["node_id"],
                }
            })
        return out


class CommentEnumerator(ArtifactEnumerator):

    PATHS = {
        "IssueComments": "/repos/{owner}/{repo}/issues/comments",
        "PRComments": "/repos/{owner}/{repo}/pulls/comments",
        "CommitComments": "/repos/{owner}/{repo}/comments",
    }

    def enumerate(
        self,
        owner: str,
        repo: str,
        kind: str,
        max_pages: Optional[int] = None,
        **_,
    ) -> List[Dict[str, Any]]:
        path = self.PATHS[kind].format(owner=owner, repo=repo)
        out = []

        for item in self.client.paginate(path, max_pages=max_pages):
            out.append({
                "artifactClass": kind,
                "identifierTuple": {
                    "owner": owner,
                    "repo": repo,
                    "comment_id": item["id"],
                    "node_id": item["node_id"],
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
        for item in self.client.paginate(
            f"/repos/{owner}/{repo}/commits",
            max_pages=max_pages,
        ):
            out.append({
                "artifactClass": "Commits",
                "identifierTuple": {
                    "owner": owner,
                    "repo": repo,
                    "sha": item["sha"],
                    "node_id": item["node_id"],
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
    "IssueComments": CommentEnumerator,
    "PRComments": CommentEnumerator,
    "CommitComments": CommentEnumerator,
    "Commits": CommitEnumerator,
}


# -------------------------------------------------------------------
# Snapshot Builder
# -------------------------------------------------------------------

def build_snapshot(
    owner: str,
    repo: str,
    include: Optional[List[str]] = None,
    limits: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    token = os.getenv(TOKEN_ENV)
    if not token:
        raise RuntimeError(f"Set {TOKEN_ENV} with a GitHub access token")

    client = GitHubRESTClient(token)
    include = include or list(ARTIFACT_ENUMERATOR_REGISTRY.keys())
    limits = limits or {}

    snapshot = {
        "repo": {"owner": owner, "repo": repo},
        "generated_at": int(time.time()),
        "artifacts": {},
    }

    for name in include:
        enum_cls = ARTIFACT_ENUMERATOR_REGISTRY[name]
        enum = enum_cls(client)

        if name.endswith("Comments"):
            snapshot["artifacts"][name] = enum.enumerate(
                owner, repo, kind=name, **limits.get(name, {})
            )
        else:
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

    lim = {}
    if args.max_pages is not None:
        for k in ARTIFACT_ENUMERATOR_REGISTRY:
            lim[k] = {"max_pages": args.max_pages}

    snap = build_snapshot(args.owner, args.repo, limits=lim)
    write_snapshot(snap, args.out)
    print(f"Snapshot written to {args.out}")
