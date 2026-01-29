"""
github_url_builder.py

Canonical GitHub URL construction for routing artifacts + benign interaction classes.
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Callable, Literal, Optional

Role = Literal["sender", "receiver"]


class GitHubURLBuilder:
    """
    Construct role-appropriate GitHub URLs for artifacts.
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
        urls = [u for u in urls if isinstance(u, str) and u.strip()]

        for url in urls:
            if "unknown" in url:
                raise RuntimeError(f"Invalid URL constructed: {url}")

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

            # NEW routing artifacts
            "GitTag": self._git_tag_urls,
            "Label": self._label_urls,
            "Milestone": self._milestone_urls,

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
    # Routing URL handlers
    # =========================================================
    def _repository_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [f"https://github.com/{self.owner}/{self.repo}"]

    def _issue_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, n = identifier
        return [f"https://github.com/{self.owner}/{self.repo}/issues/{n}"]

    def _issue_comment_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, n = identifier
        return [f"https://github.com/{self.owner}/{self.repo}/issues/{n}"]

    def _pull_request_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, n = identifier
        return [f"https://github.com/{self.owner}/{self.repo}/pull/{n}"]

    def _pull_request_comment_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, n = identifier
        return [
            f"https://github.com/{self.owner}/{self.repo}/pull/{n}",
            f"https://github.com/{self.owner}/{self.repo}/pull/{n}/files",
        ]

    def _commit_urls(self, identifier: Tuple, role: Role) -> List[str]:
        if role == "sender":
            return []
        _, _, sha = identifier
        return [f"https://github.com/{self.owner}/{self.repo}/commit/{sha}"]

    def _commit_comment_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, sha = identifier
        return [f"https://github.com/{self.owner}/{self.repo}/commit/{sha}"]

    # -------------------------
    # NEW: GitTag routing
    # -------------------------
    def _git_tag_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, tag = identifier
        return [f"https://github.com/{self.owner}/{self.repo}/releases/tag/{tag}"]

    # -------------------------
    # NEW: Label routing
    # -------------------------
    def _label_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, label = identifier
        if role == "sender":
            return [f"https://github.com/{self.owner}/{self.repo}/labels"]
        return [
            f"https://github.com/{self.owner}/{self.repo}/issues?q=state%3Aopen+label%3A%22{label}%22"
        ]

    # -------------------------
    # NEW: Milestone routing
    # -------------------------
    def _milestone_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, num = identifier
        if role == "sender":
            return [f"https://github.com/{self.owner}/{self.repo}/milestones/{num}/edit"]
        return [f"https://github.com/{self.owner}/{self.repo}/milestone/{num}"]

    # =========================================================
    # Benign URL handlers (unchanged)
    # =========================================================
    def _notifications_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        owner, repo = identifier[:2]
        return [f"https://github.com/notifications?query=repo%3A{owner}%2F{repo}+"]

    def _events_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [f"https://github.com/{self.owner}/{self.repo}/activity"]

    def _starring_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [f"https://github.com/{self.owner}/{self.repo}/stargazers"]

    def _watching_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [f"https://github.com/{self.owner}/{self.repo}/watchers"]

    def _branches_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [f"https://github.com/{self.owner}/{self.repo}/branches"]

    def _branch_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, branch = identifier
        return [f"https://github.com/{self.owner}/{self.repo}/tree/{branch}"]

    def _commits_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, branch = identifier
        return [f"https://github.com/{self.owner}/{self.repo}/commits/{branch}"]

    def _actions_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [f"https://github.com/{self.owner}/{self.repo}/actions/new"]

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

    def _milestones_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [f"https://github.com/{self.owner}/{self.repo}/milestones"]

    def _labels_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [f"https://github.com/{self.owner}/{self.repo}/labels"]

    def _git_tags_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        return [
            f"https://github.com/{self.owner}/{self.repo}/tags",
            f"https://github.com/{self.owner}/{self.repo}/releases",
        ]

    def _tag_benign_urls(self, identifier: Tuple, role: Role) -> List[str]:
        _, _, tag = identifier
        return [f"https://github.com/{self.owner}/{self.repo}/tree/{tag}"]

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
