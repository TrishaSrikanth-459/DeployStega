"""
Role-aware GitHub URL enumeration for artifact identifiers.

Responsibilities:
- Map an artifact identifier to all valid GitHub web URLs allowed for a given role
  according to namespace.md (sender vs receiver addressability).

Non-responsibilities:
- No behavioral feasibility filtering
- No timing / epoch logic
- No payload logic
- No live GitHub/API access
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Literal

Role = Literal["sender", "receiver"]


@dataclass(frozen=True)
class GitHubURLBuilder:
    owner: str
    repo: str

    def urls_for(self, artifact_class: str, identifier: Tuple, role: Role) -> List[str]:
        """
        Return all GitHub URLs for the artifact identifier that are allowed
        for the given role by the routing namespace spec.
        """
        role = self._validate_role(role)
        handler = self._handlers().get(artifact_class)
        if handler is None:
            raise KeyError(f"No URL handler for artifact class: {artifact_class}")
        return handler(identifier, role)

    # -------------------------
    # Internal helpers
    # -------------------------

    def _validate_role(self, role: str) -> Role:
        if role not in ("sender", "receiver"):
            raise ValueError(f"Invalid role: {role}. Expected 'sender' or 'receiver'.")
        return role  # type: ignore[return-value]

    def _assert_repo(self, ident_owner: str, ident_repo: str) -> None:
        # The builder is configured for one repo; identifiers should match.
        if ident_owner != self.owner or ident_repo != self.repo:
            raise ValueError(
                f"Identifier repo mismatch: got ({ident_owner}, {ident_repo}) "
                f"but builder is configured for ({self.owner}, {self.repo})."
            )

    def _branch_token(self, branch: str) -> str:
        """
        Namespace rule: for branch names used in compare URLs, replace spaces with '-'.
        """
        return branch.replace(" ", "-")

    def _handlers(self):
        return {
            "Repository": self._repository_urls,
            "Issue": self._issue_urls,
            "PullRequest": self._pull_request_urls,
            "Commit": self._commit_urls,
            "IssueComment": self._issue_comment_urls,
            "PullRequestComment": self._pull_request_comment_urls,
            "CommitComment": self._commit_comment_urls,
        }

    # -------------------------
    # Artifact handlers
    # -------------------------

    # Repository: (owner, repo)
    def _repository_urls(self, ident: Tuple, role: Role) -> List[str]:
        ident_owner, ident_repo = ident
        self._assert_repo(ident_owner, ident_repo)
        # Sender and receiver both just "retrieve/view" the repo via same URL.
        return [f"https://github.com/{self.owner}/{self.repo}"]

    # Issue: (owner, repo, issue_number)
    def _issue_urls(self, ident: Tuple, role: Role) -> List[str]:
        ident_owner, ident_repo, issue_number = ident
        self._assert_repo(ident_owner, ident_repo)

        base = f"https://github.com/{self.owner}/{self.repo}/issues/{issue_number}"

        if role == "sender":
            # Sender addressability includes: create new issue + modify existing issue
            # Your spec: create = /issues/new ; modify = visit /issues/{n} then click Edit.
            return [
                f"https://github.com/{self.owner}/{self.repo}/issues/new",
                base,
            ]

        # Receiver: access specific issue
        return [base]

    # PullRequest: (owner, repo, pull_number, branch_1, branch_2)
    def _pull_request_urls(self, ident: Tuple, role: Role) -> List[str]:
        ident_owner, ident_repo, pull_number, branch_1, branch_2 = ident
        self._assert_repo(ident_owner, ident_repo)

        pr_page = f"https://github.com/{self.owner}/{self.repo}/pull/{pull_number}"

        if role == "sender":
            # Sender addressability includes:
            # - create PR: /compare/{branch_1}...{branch_2}
            # - modify fields: visit /pull/{n}
            # - merge: visit /pull/{n}
            b1 = self._branch_token(branch_1)
            b2 = self._branch_token(branch_2)
            compare = f"https://github.com/{self.owner}/{self.repo}/compare/{b1}...{b2}"
            return [compare, pr_page]

        # Receiver: view PR
        return [pr_page]

    # Commit: (owner, repo, branch, path, commit_sha)
    def _commit_urls(self, ident: Tuple, role: Role) -> List[str]:
        ident_owner, ident_repo, branch, path, commit_sha = ident
        self._assert_repo(ident_owner, ident_repo)

        if role == "sender":
            # Sender addressability includes editing/creating files via web UI:
            # - edit existing: /edit/{branch}/{path}
            # - create new file: /new/{branch}/{path}
            return [
                f"https://github.com/{self.owner}/{self.repo}/edit/{branch}/{path}",
                f"https://github.com/{self.owner}/{self.repo}/new/{branch}/{path}",
            ]

        # Receiver: access commit by SHA
        return [f"https://github.com/{self.owner}/{self.repo}/commit/{commit_sha}"]

    # IssueComment: (owner, repo, issue_number)
    def _issue_comment_urls(self, ident: Tuple, role: Role) -> List[str]:
        ident_owner, ident_repo, issue_number = ident
        self._assert_repo(ident_owner, ident_repo)

        # Your spec for sender/receiver both uses the issue page URL;
        # comment-level operations happen via UI elements on that page.
        return [f"https://github.com/{self.owner}/{self.repo}/issues/{issue_number}"]

    # PullRequestComment: (owner, repo, pull_number)
    def _pull_request_comment_urls(self, ident: Tuple, role: Role) -> List[str]:
        ident_owner, ident_repo, pull_number = ident
        self._assert_repo(ident_owner, ident_repo)

        convo = f"https://github.com/{self.owner}/{self.repo}/pull/{pull_number}"
        files = f"https://github.com/{self.owner}/{self.repo}/pull/{pull_number}/files"

        if role == "sender":
            # Sender can create/edit convo comments on /pull/{n}
            # and create/reply/edit review comments on /pull/{n}/files
            return [convo, files]

        # Receiver can view convo comments on /pull/{n}
        # and view review comments on /pull/{n}/files
        return [convo, files]

    # CommitComment: (owner, repo, commit_sha)
    def _commit_comment_urls(self, ident: Tuple, role: Role) -> List[str]:
        ident_owner, ident_repo, commit_sha = ident
        self._assert_repo(ident_owner, ident_repo)

        # Sender and receiver both use the commit page URL; actions are UI-driven.
        return [f"https://github.com/{self.owner}/{self.repo}/commit/{commit_sha}"]
