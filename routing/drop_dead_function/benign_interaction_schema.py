"""
benign_interaction_schema.py

Benign Interaction Namespace (resolver-selected noise).

These interactions:
- are repository-scoped
- never encode payload
- are not snapshot-enumerated
- are selected per epoch by a (future) benign trace model

We model each benign interaction class as a name + URL template set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple
from urllib.parse import quote


@dataclass(frozen=True)
class BenignInteractionClass:
    name: str
    # identifier fields are always (owner, repo) or (owner, repo, branch/tag/etc.)
    # but benign interactions are NOT validated against routing schemas.
    # We'll keep deterministic URL construction separate from routing URL builder.


def repo_scoped_urls(owner: str, repo: str) -> Dict[str, List[str]]:
    """
    Returns benign interaction class -> list of GUI URLs (your spec).
    """
    return {
        "Notifications_Benign": [
            f"https://github.com/notifications?query=repo%3A{quote(owner, safe='')}%2F{quote(repo, safe='')}+"
        ],
        "Events_Benign": [
            f"https://github.com/{owner}/{repo}/activity"
        ],
        "Starring_Benign": [
            f"https://github.com/{owner}/{repo}/stargazers"
        ],
        "Watching_Benign": [
            f"https://github.com/{owner}/{repo}/watchers"
        ],
        "Branches_Benign": [
            f"https://github.com/{owner}/{repo}/branches",
        ],
        "Actions": [
            f"https://github.com/{owner}/{repo}/actions/new",
        ],
        "RepositoryGovernanceSettings_Benign": [
            f"https://github.com/{owner}/{repo}/settings",
            f"https://github.com/{owner}/{repo}/settings/access",
            f"https://github.com/{owner}/{repo}/settings/branches",
            f"https://github.com/{owner}/{repo}/settings/tag_protection",
            f"https://github.com/{owner}/{repo}/settings/rules",
        ],
        "AutomationAndExecutionSettings_Benign": [
            f"https://github.com/{owner}/{repo}/settings/actions",
            f"https://github.com/{owner}/{repo}/settings/actions/runners",
            f"https://github.com/{owner}/{repo}/settings/environments",
        ],
        "SecurityAndSecretsSettings_Benign": [
            f"https://github.com/{owner}/{repo}/settings/security_analysis",
            f"https://github.com/{owner}/{repo}/settings/keys",
            f"https://github.com/{owner}/{repo}/settings/secrets/actions",
            f"https://github.com/{owner}/{repo}/settings/secrets/codespaces",
            f"https://github.com/{owner}/{repo}/settings/secrets/dependabot",
        ],
        "IntegrationsAndExtensionsSettings_Benign": [
            f"https://github.com/{owner}/{repo}/settings/hooks",
            f"https://github.com/{owner}/{repo}/settings/installations",
            f"https://github.com/{owner}/{repo}/settings/codespaces",
        ],
        "AIAndModelPolicySettings_Benign": [
            f"https://github.com/{owner}/{repo}/settings/copilot/code_review",
            f"https://github.com/{owner}/{repo}/settings/copilot/coding_agent",
            f"https://github.com/{owner}/{repo}/settings/models/access-policy",
        ],
        "PublishingAndNotificationSettings_Benign": [
            f"https://github.com/{owner}/{repo}/settings/pages",
        ],
        "RepositorySecurity_Benign": [
            f"https://github.com/{owner}/{repo}/security",
        ],
        "DependencyNetworkInspection_Benign": [
            f"https://github.com/{owner}/{repo}/network/dependencies",
            f"https://github.com/{owner}/{repo}/network/updates",
            f"https://github.com/{owner}/{repo}/network/members",
        ],
        "Forks_Benign": [
            f"https://github.com/{owner}/{repo}/forks",
        ],
        "Milestones_Benign": [
            f"https://github.com/{owner}/{repo}/milestones",
        ],
        "Labels_Benign": [
            f"https://github.com/{owner}/{repo}/labels",
        ],
        "GitTags_Benign": [
            f"https://github.com/{owner}/{repo}/tags",
            f"https://github.com/{owner}/{repo}/releases",
        ],
        "PullRequests_Benign": [
            f"https://github.com/{owner}/{repo}/pulls",
        ],
        "Issues_Benign": [
            f"https://github.com/{owner}/{repo}/issues",
        ],
    }
