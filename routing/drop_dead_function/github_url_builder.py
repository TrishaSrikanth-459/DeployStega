"""
github_url_builder.py

Canonical GitHub URL construction for routing artifacts + benign interaction classes.

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

from typing import Dict, List, Tuple, Callable, Literal, Optional

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

        # HARD SAFETY: never emit placeholder URLs
        for url in urls:
            if "unknown" in url:
                raise RuntimeError(f"Invalid URL constructed (contains 'unknown'): {url}")

        return urls

    # =========================================================
    # Handler registry
    # =========================================================
    def _handlers(self) -> Dict[str, Callable[[Tuple, Role], List[str]]]:
        return {
            # -------------------------
            # Routing / mutative
            # -------------------------
            "Repository": self._repository_urls,
            "Issue": self._issue_urls,
            "IssueComment": self._issue_comment_urls,
            "PullRequest": self._pull_request_urls,
            "PullRequestComment": self._pull_request_comment_urls,
            "Commit": self._commit_urls,
            "CommitComment": self._commit_comment_urls,

            # -------------------------
            # Benign interaction classes
            # -------------------------
            "Notifications_Benign": self._notifications_benign_urls,
            "Events_Benign": self._events_benign_urls,
            "Starring_Benign": self._starring_benign_urls,
            "Watching_Benign": self._watching_benign_urls,

            "Branches_Benign": self._branches_benign_urls,
            "Branch_Benign": self._branch_benign_urls,
            "Commits_Benign": self._commits_benign_urls,

            "Actions_Benign": self._actions_benign_urls,

            "RepositoryGovernanceSettings_Benign": self._repo_governance_settings_benign_urls,
            "AutomationAndExecutionSettings_Benign": self._automation_execution_settings_benign_urls,
            "SecurityAndSecretsSettings_Benign": self._security_secrets_settings_benign_urls,
            "IntegrationsAndExtensionsSettings_Benign": self._integrations_extensions_settings_benign_urls,
            "AIAndModelPolicySettings_Benign": self._ai_model_policy_settings_benign_urls,
            "PublishingAndNotificationSettings_Benign": self._publishing_notification_settings_benign_urls,

            "RepositorySecurity_Benign": self._repository_security_benign_urls,

            "DependencyNetworkInspection_Benign": self._dependency_network_inspection_benign_urls,
            "Forks_Benign": self._forks_benign_urls,

            "Milestones_Benign": self._milestones_benign_urls,
            "Labels_Benign": self._labels_benign_urls,

            "GitTags_Benign": self._git_tags_benign_urls,
            "Tag_Benign": self._tag_benign_urls,

            "PullRequests_Benign": self._pull_requests_benign_urls,
            "Issues_Benign": self._issues_benign_urls,
        }

    # =========================================================
    # Routing URL handlers (schema-aligned)
    # =========================================================
    def _repository_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo)
        return [f"https://github.com/{self.owner}/{self.repo}"]

    def _issue_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo, issue_number)
        _, _, issue_number = identifier
        return [f"https://github.com/{self.owner}/{self.repo}/issues/{issue_number}"]

    def _issue_comment_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo, issue_number)
        _, _, issue_number = identifier
        return [f"https://github.com/{self.owner}/{self.repo}/issues/{issue_number}"]

    def _pull_request_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo, pull_number)
        _, _, pull_number = identifier
        return [f"https://github.com/{self.owner}/{self.repo}/pull/{pull_number}"]

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
    @staticmethod
    def _extract_commit_sha(identifier: Tuple) -> Optional[str]:
        """
        Commit namespace may be:
        - NEW: (owner, repo, commit_sha)
        - OLD: (owner, repo, branch, path, commit_sha)

        Return commit_sha if extractable, else None.
        """
        if len(identifier) == 3:
            _, _, commit_sha = identifier
            return commit_sha if isinstance(commit_sha, str) and commit_sha.strip() else None
        if len(identifier) == 5:
            commit_sha = identifier[4]
            return commit_sha if isinstance(commit_sha, str) and commit_sha.strip() else None
        return None

    def _commit_urls(self, identifier: Tuple, role: Role) -> List[str]:
        commit_sha = self._extract_commit_sha(identifier)
        if commit_sha is None:
            return []

        # IMPORTANT NAMESPACE RULE:
        # Commits are receiver-only artifacts in the identifier-preserving model.
        if role == "sender":
            return []

        return [f"https://github.com/{self.owner}/{self.repo}/commit/{commit_sha}"]

    def _commit_comment_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo, commit_sha)
        _, _, commit_sha = identifier
        if not isinstance(commit_sha, str) or not commit_sha.strip():
            return []
        return [f"https://github.com/{self.owner}/{self.repo}/commit/{commit_sha}"]

    # =========================================================
    # Benign interaction URL handlers
    # =========================================================
    def _notifications_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo)
        owner, repo = identifier[0], identifier[1]
        # Note: query is treated as presentation-layer; this is the canonical surface.
        return [f"https://github.com/notifications?query=repo%3A{owner}%2F{repo}+"]

    def _events_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo)
        return [f"https://github.com/{self.owner}/{self.repo}/activity"]

    def _starring_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo)
        return [f"https://github.com/{self.owner}/{self.repo}/stargazers"]

    def _watching_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo)
        return [f"https://github.com/{self.owner}/{self.repo}/watchers"]

    # -------------------------
    # Branches benign
    # -------------------------
    def _branches_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo)
        return [f"https://github.com/{self.owner}/{self.repo}/branches"]

    def _branch_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo, branch)
        _, _, branch = identifier
        return [f"https://github.com/{self.owner}/{self.repo}/tree/{branch}"]

    def _commits_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo, branch)
        _, _, branch = identifier
        return [f"https://github.com/{self.owner}/{self.repo}/commits/{branch}"]

    # -------------------------
    # Actions benign
    # -------------------------
    def _actions_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [f"https://github.com/{self.owner}/{self.repo}/actions/new"]

    # -------------------------
    # Settings benign (multiple URL surfaces per class)
    # -------------------------
    def _repo_governance_settings_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [
            f"https://github.com/{self.owner}/{self.repo}/settings",
            f"https://github.com/{self.owner}/{self.repo}/settings/access",
            f"https://github.com/{self.owner}/{self.repo}/settings/branches",
            f"https://github.com/{self.owner}/{self.repo}/settings/tag_protection",
            f"https://github.com/{self.owner}/{self.repo}/settings/rules",
        ]

    def _automation_execution_settings_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [
            f"https://github.com/{self.owner}/{self.repo}/settings/actions",
            f"https://github.com/{self.owner}/{self.repo}/settings/actions/runners",
            f"https://github.com/{self.owner}/{self.repo}/settings/environments",
        ]

    def _security_secrets_settings_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [
            f"https://github.com/{self.owner}/{self.repo}/settings/security_analysis",
            f"https://github.com/{self.owner}/{self.repo}/settings/keys",
            f"https://github.com/{self.owner}/{self.repo}/settings/secrets/actions",
            f"https://github.com/{self.owner}/{self.repo}/settings/secrets/codespaces",
            f"https://github.com/{self.owner}/{self.repo}/settings/secrets/dependabot",
        ]

    def _integrations_extensions_settings_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [
            f"https://github.com/{self.owner}/{self.repo}/settings/hooks",
            f"https://github.com/{self.owner}/{self.repo}/settings/installations",
            f"https://github.com/{self.owner}/{self.repo}/settings/codespaces",
        ]

    def _ai_model_policy_settings_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [
            f"https://github.com/{self.owner}/{self.repo}/settings/copilot/code_review",
            f"https://github.com/{self.owner}/{self.repo}/settings/copilot/coding_agent",
            f"https://github.com/{self.owner}/{self.repo}/settings/models/access-policy",
        ]

    def _publishing_notification_settings_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [f"https://github.com/{self.owner}/{self.repo}/settings/pages"]

    # -------------------------
    # Security / dependency / forks benign
    # -------------------------
    def _repository_security_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [f"https://github.com/{self.owner}/{self.repo}/security"]

    def _dependency_network_inspection_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [
            f"https://github.com/{self.owner}/{self.repo}/network/dependencies",
            f"https://github.com/{self.owner}/{self.repo}/network/updates",
            f"https://github.com/{self.owner}/{self.repo}/network/members",
        ]

    def _forks_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [f"https://github.com/{self.owner}/{self.repo}/forks"]

    # -------------------------
    # Milestones / labels benign
    # -------------------------
    def _milestones_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [f"https://github.com/{self.owner}/{self.repo}/milestones"]

    def _labels_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [f"https://github.com/{self.owner}/{self.repo}/labels"]

    # -------------------------
    # Tags / releases benign
    # -------------------------
    def _git_tags_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [
            f"https://github.com/{self.owner}/{self.repo}/tags",
            f"https://github.com/{self.owner}/{self.repo}/releases",
        ]

    def _tag_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        # identifier = (owner, repo, tag)
        _, _, tag = identifier
        return [f"https://github.com/{self.owner}/{self.repo}/tree/{tag}"]

    # -------------------------
    # PR/issues list benign
    # -------------------------
    def _pull_requests_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [f"https://github.com/{self.owner}/{self.repo}/pulls"]

    def _issues_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [f"https://github.com/{self.owner}/{self.repo}/issues"]

    # =========================================================
    # Role validation
    # =========================================================
    @staticmethod
    def _validate_role(role: Role) -> Role:
        if role not in ("sender", "receiver"):
            raise ValueError(f"Invalid role: {role}")
        return role
