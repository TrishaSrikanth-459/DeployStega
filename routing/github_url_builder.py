"""
Deterministic construction of role-specific GitHub URLs
from artifact identifiers.

Responsibilities:
- Map identifiers to GitHub URLs
- Select URLs appropriate to sender vs receiver behavior

Non-responsibilities:
- No timing
- No routing logic
- No existence checks
"""

from __future__ import annotations
from typing import Tuple


class GitHubURLBuilder:
    def __init__(self, owner: str, repo: str):
        self.owner = owner
        self.repo = repo

    # -------------------------
    # Public interface
    # -------------------------

    def build_url(
        self,
        artifact_class: str,
        identifier: Tuple,
        role: str,
    ) -> str:
        """
        Construct a role-appropriate GitHub URL.

        role ∈ {"sender", "receiver"}
        """
        if role not in {"sender", "receiver"}:
            raise ValueError(f"Invalid role: {role}")

        handler = self._handlers().get(artifact_class)
        if handler is None:
            raise KeyError(f"No URL handler for artifact class: {artifact_class}")

        return handler(identifier, role)

    # -------------------------
    # Artifact-specific handlers
    # -------------------------

    def _handlers(self):
        return {
            "Issues": self._issue_url,
            "IssueComments": self._issue_comment_url,
            "PullRequests": self._pull_request_url,
            "PRComments": self._pr_comment_url,
            "Commits": self._commit_url,
            "CommitComments": self._commit_comment_url,
            "Discussions": self._discussion_url,
            "DiscussionComments": self._discussion_comment_url,
        }

    # ---- Issues ----

    def _issue_url(self, ident: Tuple, role: str) -> str:
        (_, issue_number) = ident
        base = f"https://github.com/{self.owner}/{self.repo}/issues/{issue_number}"

        if role == "sender":
            return f"{base}/edit"
        return base

    def _issue_comment_url(self, ident: Tuple, role: str) -> str:
        (_, issue_number, comment_id) = ident
        base = (
            f"https://github.com/{self.owner}/{self.repo}"
            f"/issues/{issue_number}#issuecomment-{comment_id}"
        )

        # Sender replies by loading issue page
        if role == "sender":
            return f"https://github.com/{self.owner}/{self.repo}/issues/{issue_number}"
        return base

    # ---- Pull Requests ----

    def _pull_request_url(self, ident: Tuple, role: str) -> str:
        (_, pr_number) = ident
        base = f"https://github.com/{self.owner}/{self.repo}/pull/{pr_number}"

        if role == "sender":
            return f"{base}/edit"
        return base

    def _pr_comment_url(self, ident: Tuple, role: str) -> str:
        (_, pr_number, comment_id) = ident
        base = (
            f"https://github.com/{self.owner}/{self.repo}"
            f"/pull/{pr_number}#discussion_r{comment_id}"
        )

        if role == "sender":
            return f"https://github.com/{self.owner}/{self.repo}/pull/{pr_number}"
        return base

    # ---- Commits ----

    def _commit_url(self, ident: Tuple, role: str) -> str:
        (_, commit_sha) = ident
        base = (
            f"https://github.com/{self.owner}/{self.repo}/commit/{commit_sha}"
        )

        # Sender editing occurs via file edit URLs, not commit URLs
        return base

    def _commit_comment_url(self, ident: Tuple, role: str) -> str:
        (_, commit_sha, comment_id) = ident
        return (
            f"https://github.com/{self.owner}/{self.repo}"
            f"/commit/{commit_sha}#commitcomment-{comment_id}"
        )

    # ---- Discussions ----

    def _discussion_url(self, ident: Tuple, role: str) -> str:
        (_, discussion_number) = ident
        return (
            f"https://github.com/{self.owner}/{self.repo}"
            f"/discussions/{discussion_number}"
        )

    def _discussion_comment_url(self, ident: Tuple, role: str) -> str:
        (_, discussion_number, comment_id) = ident
        return (
            f"https://github.com/{self.owner}/{self.repo}"
            f"/discussions/{discussion_number}?commentId={comment_id}"
        )
