"""
github_url_builder.py

Canonical GitHub URL construction for routing artifacts.

This module:
- Maps artifact classes to URL constructors
- Enforces role validity
- Contains NO snapshot or feasibility logic
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Callable, Literal

Role = Literal["sender", "receiver"]


class GitHubURLBuilder:
    """
    Construct role-appropriate GitHub URLs for artifacts.

    IMPORTANT INVARIANT:
    - artifact_class MUST be the canonical ArtifactClass.name
      (e.g. "Issues", "PullRequests")
    """

    def __init__(self, *, owner: str, repo: str):
        self.owner = owner
        self.repo = repo

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def urls_for(
        self,
        artifact_class: str,
        identifier: Tuple,
        role: Role,
    ) -> List[str]:
        """
        Return all GitHub URLs for the artifact identifier that are allowed
        by the routing namespace spec for the given role.
        """
        role = self._validate_role(role)

        handler = self._handlers().get(artifact_class)
        if handler is None:
            raise KeyError(f"No URL handler for artifact class: {artifact_class}")

        return handler(identifier, role)

    # ---------------------------------------------------------
    # Handler registry (CANONICAL)
    # ---------------------------------------------------------

    def _handlers(self) -> Dict[str, Callable[[Tuple, Role], List[str]]]:
        """
        Map canonical artifact class names to URL handlers.
        """
        return {
            "Repositories": self._repository_urls,
            "Issues": self._issue_urls,
            "PullRequests": self._pull_request_urls,
            "Commits": self._commit_urls,
            "IssueComments": self._issue_comment_urls,
            "PRComments": self._pull_request_comment_urls,
            "CommitComments": self._commit_comment_urls,
            "Discussions": self._discussion_urls,
            "DiscussionComments": self._discussion_comment_urls,
        }

    # ---------------------------------------------------------
    # URL handlers
    # ---------------------------------------------------------

    def _repository_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [
            f"https://github.com/{self.owner}/{self.repo}"
        ]

    def _issue_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, issue_number = identifier
        return [
            f"https://github.com/{self.owner}/{self.repo}/issues/{issue_number}"
        ]

    def _pull_request_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, pull_number = identifier
        return [
            f"https://github.com/{self.owner}/{self.repo}/pull/{pull_number}"
        ]

    def _commit_urls(self, identifier: Tuple, role: Role) -> List[str]:
        *_, commit_sha = identifier
        return [
            f"https://github.com/{self.owner}/{self.repo}/commit/{commit_sha}"
        ]

    def _issue_comment_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, issue_number, comment_id = identifier
        return [
            f"https://github.com/{self.owner}/{self.repo}/issues/{issue_number}#issuecomment-{comment_id}"
        ]

    def _pull_request_comment_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, pull_number, comment_id = identifier
        return [
            f"https://github.com/{self.owner}/{self.repo}/pull/{pull_number}#discussion_r{comment_id}"
        ]

    def _commit_comment_urls(self, identifier: Tuple, role: Role) -> List[str]:
        *_, commit_sha, comment_id = identifier
        return [
            f"https://github.com/{self.owner}/{self.repo}/commit/{commit_sha}#commitcomment-{comment_id}"
        ]

    def _discussion_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, discussion_number = identifier
        return [
            f"https://github.com/{self.owner}/{self.repo}/discussions/{discussion_number}"
        ]

    def _discussion_comment_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, discussion_number, comment_id = identifier
        return [
            f"https://github.com/{self.owner}/{self.repo}/discussions/{discussion_number}#discussioncomment-{comment_id}"
        ]

    # ---------------------------------------------------------
    # Role validation
    # ---------------------------------------------------------

    @staticmethod
    def _validate_role(role: Role) -> Role:
        if role not in ("sender", "receiver"):
            raise ValueError(f"Invalid role: {role}")
        return role
