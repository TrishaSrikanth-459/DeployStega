"""
enumerators.py

Snapshot Construction Enumerators (REST API ONLY) — UPDATED.

All enumeration occurs pre-experiment.
Only REAL, addressable, identifier-valid artifacts are emitted.

Outputs are intended to be fed into RepositorySnapshot.from_enumeration().
"""

from __future__ import annotations

import os
from typing import Dict, List, Any, Optional, Iterable, Set
import requests

from schema import ArtifactClass


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
        return [
            {
                "artifactClass": "Repository",
                "identifierTuple": {"owner": owner, "repo": repo},
            }
        ]


class IssueEnumerator:
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for issue in self.client.paginate(f"/repos/{owner}/{repo}/issues", params={"state": "all"}):
            if "pull_request" in issue:
                continue
            out.append(
                {
                    "artifactClass": "Issue",
                    "identifierTuple": {
                        "owner": owner,
                        "repo": repo,
                        "issue_number": issue["number"],
                    },
                }
            )
        return out


class IssueCommentEnumerator:
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        # enumerate issues and emit IssueComment only if issue has at least 1 comment
        for issue in self.client.paginate(f"/repos/{owner}/{repo}/issues", params={"state": "all"}):
            if "pull_request" in issue:
                continue
            issue_number = issue["number"]
            comments_url = f"/repos/{owner}/{repo}/issues/{issue_number}/comments"
            # one page is enough to detect existence
            comments = list(self.client.paginate(comments_url, per_page=1, max_pages=1))
            if comments:
                out.append(
                    {
                        "artifactClass": "IssueComment",
                        "identifierTuple": {"owner": owner, "repo": repo, "issue_number": issue_number},
                    }
                )
        return out


class PullRequestEnumerator:
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for pr in self.client.paginate(f"/repos/{owner}/{repo}/pulls", params={"state": "all"}):
            out.append(
                {
                    "artifactClass": "PullRequest",
                    "identifierTuple": {"owner": owner, "repo": repo, "pull_number": pr["number"]},
                }
            )
        return out


class PullRequestCommentEnumerator:
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """
        PullRequestComment corresponds to review comments (inline) in your namespace.
        We emit it if the PR has at least one review comment.
        """
        out: List[Dict[str, Any]] = []
        for pr in self.client.paginate(f"/repos/{owner}/{repo}/pulls", params={"state": "all"}):
            pull_number = pr["number"]
            # Review comments endpoint:
            comments_path = f"/repos/{owner}/{repo}/pulls/{pull_number}/comments"
            comments = list(self.client.paginate(comments_path, per_page=1, max_pages=1))
            if comments:
                out.append(
                    {
                        "artifactClass": "PullRequestComment",
                        "identifierTuple": {"owner": owner, "repo": repo, "pull_number": pull_number},
                    }
                )
        return out


class CommitEnumerator:
    """
    UPDATED Commit enumerator (namespace-aligned):
    identifierTuple = (owner, repo, branch, commit_sha)

    We enumerate branches, then commits per branch.
    """
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen: Set[tuple] = set()

        for branch_obj in self.client.paginate(f"/repos/{owner}/{repo}/branches"):
            branch = branch_obj.get("name")
            if not branch:
                continue

            for commit in self.client.paginate(f"/repos/{owner}/{repo}/commits", params={"sha": branch}):
                commit_sha = commit.get("sha")
                if not commit_sha:
                    continue

                key = (branch, commit_sha)
                if key in seen:
                    continue
                seen.add(key)

                out.append(
                    {
                        "artifactClass": "Commit",
                        "identifierTuple": {
                            "owner": owner,
                            "repo": repo,
                            "branch": branch,
                            "commit_sha": commit_sha,
                        },
                    }
                )

        return out


class CommitCommentEnumerator:
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """
        Emit CommitComment if the commit has at least one commit comment.
        We enumerate recent commits via /commits and then check /commits/{sha}/comments.
        """
        out: List[Dict[str, Any]] = []
        seen: Set[str] = set()

        for commit in self.client.paginate(f"/repos/{owner}/{repo}/commits"):
            commit_sha = commit.get("sha")
            if not commit_sha or commit_sha in seen:
                continue
            seen.add(commit_sha)

            comments_path = f"/repos/{owner}/{repo}/commits/{commit_sha}/comments"
            comments = list(self.client.paginate(comments_path, per_page=1, max_pages=1))
            if comments:
                out.append(
                    {
                        "artifactClass": "CommitComment",
                        "identifierTuple": {"owner": owner, "repo": repo, "commit_sha": commit_sha},
                    }
                )

        return out


class GitTagEnumerator:
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for tag in self.client.paginate(f"/repos/{owner}/{repo}/tags"):
            name = tag.get("name")
            if not name:
                continue
            out.append(
                {
                    "artifactClass": "GitTag",
                    "identifierTuple": {"owner": owner, "repo": repo, "tag": name},
                }
            )
        return out


class LabelEnumerator:
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for label in self.client.paginate(f"/repos/{owner}/{repo}/labels"):
            name = label.get("name")
            if not name:
                continue
            out.append(
                {
                    "artifactClass": "Label",
                    "identifierTuple": {"owner": owner, "repo": repo, "label_name": name},
                }
            )
        return out


class MilestoneEnumerator:
    def __init__(self, client: GitHubRESTClient):
        self.client = client

    def enumerate(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for ms in self.client.paginate(f"/repos/{owner}/{repo}/milestones", params={"state": "all"}):
            number = ms.get("number")
            if not isinstance(number, int):
                continue
            out.append(
                {
                    "artifactClass": "Milestone",
                    "identifierTuple": {"owner": owner, "repo": repo, "milestone_number": number},
                }
            )
        return out


# -------------------------------------------------------------------
# Snapshot Builder
# -------------------------------------------------------------------

def build_snapshot(owner: str, repo: str) -> Dict[str, Any]:
    token = os.getenv(TOKEN_ENV)
    if not token:
        raise RuntimeError(f"Set {TOKEN_ENV} with a GitHub access token")

    client = GitHubRESTClient(token)

    snapshot: Dict[str, Any] = {"artifacts": {}}

    snapshot["artifacts"]["Repository"] = RepositoryEnumerator().enumerate(owner, repo)

    snapshot["artifacts"]["Issue"] = IssueEnumerator(client).enumerate(owner, repo)
    snapshot["artifacts"]["IssueComment"] = IssueCommentEnumerator(client).enumerate(owner, repo)

    snapshot["artifacts"]["PullRequest"] = PullRequestEnumerator(client).enumerate(owner, repo)
    snapshot["artifacts"]["PullRequestComment"] = PullRequestCommentEnumerator(client).enumerate(owner, repo)

    snapshot["artifacts"]["Commit"] = CommitEnumerator(client).enumerate(owner, repo)
    snapshot["artifacts"]["CommitComment"] = CommitCommentEnumerator(client).enumerate(owner, repo)

    snapshot["artifacts"]["GitTag"] = GitTagEnumerator(client).enumerate(owner, repo)
    snapshot["artifacts"]["Label"] = LabelEnumerator(client).enumerate(owner, repo)
    snapshot["artifacts"]["Milestone"] = MilestoneEnumerator(client).enumerate(owner, repo)

    # HARD FILTER: remove empty artifact classes
    snapshot["artifacts"] = {cls: items for cls, items in snapshot["artifacts"].items() if items}
    return snapshot
