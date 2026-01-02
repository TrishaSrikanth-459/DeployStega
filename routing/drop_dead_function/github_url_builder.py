"""
github_url_builder.py

Canonical GitHub URL construction for routing artifacts.

This module:
- Maps ArtifactClass.name → URL constructors
- Enforces role validity
- Constructs ONLY schema-valid, identifier-faithful URLs
- NEVER invents or repairs identifiers
- NEVER emits placeholder URLs
- Returns [] if no namespace-valid URL exists for (class, identifier, role)

Non-responsibilities:
- No snapshot logic
- No feasibility logic
- No routing logic
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Callable, Literal

Role = Literal["sender", "receiver"]


class GitHubURLBuilder:
    """
    Construct role-appropriate GitHub URLs for artifacts.

    HARD INVARIANTS:
    - artifact_class MUST equal ArtifactClass.name
    - identifier MUST already be schema-valid
    - NO URL containing 'unknown' may be constructed
    - If a role has NO valid URL surface, return []
    """

    def __init__(self, *, owner: str, repo: str):
        self.owner = owner
        self.repo = repo

    # =========================================================
    # Public API
    # =========================================================

    def urls_for(
        self,
        artifact_class: str,
        identifier: Tuple,
        role: Role,
    ) -> List[str]:
        role = self._validate_role(role)

        handler = self._handlers().get(artifact_class)
        if handler is None:
            raise KeyError(f"No URL handler for artifact class: {artifact_class}")

        urls = handler(identifier, role)

        # Normalize
        urls = [u for u in urls if isinstance(u, str) and u.strip()]

        for url in urls:
            if "unknown" in url:
                raise RuntimeError(
                    f"Invalid URL constructed (contains 'unknown'): {url}"
                )

        return urls

    # =========================================================
    # Handler registry
    # =========================================================

    def _handlers(self) -> Dict[str, Callable[[Tuple, Role], List[str]]]:
        return {
            "Repository": self._repository_urls,
            "Issue": self._issue_urls,
            "IssueComment": self._issue_comment_urls,
            "PullRequest": self._pull_request_urls,
            "PullRequestComment": self._pull_request_comment_urls,
            "Commit": self._commit_urls,
            "CommitComment": self._commit_comment_urls,
        }

    # =========================================================
    # URL handlers (SCHEMA-ALIGNED)
    # =========================================================

    # -------------------------
    # Repository
    # -------------------------

    def _repository_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo)
        return [
            f"https://github.com/{self.owner}/{self.repo}"
        ]

    # -------------------------
    # Issue
    # -------------------------

    def _issue_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo, issue_number)
        _, _, issue_number = identifier
        return [
            f"https://github.com/{self.owner}/{self.repo}/issues/{issue_number}"
        ]

    # -------------------------
    # Issue Comment
    # -------------------------

    def _issue_comment_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo, issue_number)
        _, _, issue_number = identifier
        return [
            f"https://github.com/{self.owner}/{self.repo}/issues/{issue_number}"
        ]

    # -------------------------
    # Pull Request
    # -------------------------

    def _pull_request_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo, pull_number)
        _, _, pull_number = identifier
        return [
            f"https://github.com/{self.owner}/{self.repo}/pull/{pull_number}"
        ]

    # -------------------------
    # Pull Request Comment
    # -------------------------

    def _pull_request_comment_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo, pull_number)
        _, _, pull_number = identifier
        return [
            f"https://github.com/{self.owner}/{self.repo}/pull/{pull_number}",
            f"https://github.com/{self.owner}/{self.repo}/pull/{pull_number}/files",
        ]

    # -------------------------
    # Commit (receiver-only)
    # -------------------------

    def _commit_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo, branch, path, commit_sha)
        _, _, _, _, commit_sha = identifier

        if role == "sender":
            # Sender must NOT create commits (would create new commit_sha)
            return []

        return [
            f"https://github.com/{self.owner}/{self.repo}/commit/{commit_sha}"
        ]

    # -------------------------
    # Commit Comment
    # -------------------------

    def _commit_comment_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo, commit_sha)
        _, _, commit_sha = identifier
        return [
            f"https://github.com/{self.owner}/{self.repo}/commit/{commit_sha}"
        ]

    # =========================================================
    # Role validation
    # =========================================================

    @staticmethod
    def _validate_role(role: Role) -> Role:
        if role not in ("sender", "receiver"):
            raise ValueError(f"Invalid role: {role}")
        return role
