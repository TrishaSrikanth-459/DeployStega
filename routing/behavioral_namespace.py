"""
Behavioral interpretation layer for DeployStega.

This module defines constraints and interpretations that operate
ON TOP OF routing artifacts without redefining them.
"""

from typing import FrozenSet, Dict
from routing.dead_drop_function.repository_snapshot.schema import ArtifactClass


# =========================
# Observable Artifact Classes
# =========================

OBSERVABLE_ARTIFACT_CLASSES: FrozenSet[ArtifactClass] = frozenset({
    ArtifactClass.Issue,
    ArtifactClass.PullRequest,
    ArtifactClass.Commit,
    ArtifactClass.IssueComment,
    ArtifactClass.PullRequestComment,
    ArtifactClass.CommitComment,
})


# =========================
# Identifier-Preserving Constraints
# =========================

IDENTIFIER_DEFINING_FIELDS: Dict[ArtifactClass, FrozenSet[str]] = {
    ArtifactClass.Repository: frozenset({"owner", "repo"}),
    ArtifactClass.Issue: frozenset({"issue_number"}),
    ArtifactClass.PullRequest: frozenset({"pull_number"}),
    ArtifactClass.Commit: frozenset({"commit_sha"}),
    ArtifactClass.IssueComment: frozenset({"issue_number"}),
    ArtifactClass.PullRequestComment: frozenset({"pull_number"}),
    ArtifactClass.CommitComment: frozenset({"commit_sha"}),
    ArtifactClass.GitTag: frozenset({"tag"}),
    ArtifactClass.Label: frozenset({"label_name"}),
    ArtifactClass.Milestone: frozenset({"milestone_number"}),
}


# =========================
# Sender Behavioral Constraints
# =========================

FORBIDDEN_SENDER_ACTIONS: FrozenSet[str] = frozenset({
    "repository_rename",
    "issue_transfer",
    "pull_request_transfer",
    "issue_title_edit",
    "pull_request_title_edit",
    "milestone_title_edit",
    "label_name_edit",
})


ALLOWED_SENDER_ACTIONS: Frozen
