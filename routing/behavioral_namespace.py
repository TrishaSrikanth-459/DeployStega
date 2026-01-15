"""
routing/behavioral_namespace.py

Behavioral interpretation layer for DeployStega.

This module defines:
- behavioral constraints (allowed/forbidden/out-of-scope actions)
- mappings useful for behavioral feature extraction

IMPORTANT:
- This file MUST NOT redefine routing ArtifactClass or identifier schemas.
- Canonical routing schema lives in:
  routing/dead_drop_function/repository_snapshot/schema.py
"""

from __future__ import annotations

from typing import FrozenSet, Dict

from routing.dead_drop_function.repository_snapshot.schema import ArtifactClass


# -------------------------
# Identifier-preserving fields
# -------------------------

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


# -------------------------
# Behavioral constraints
# -------------------------

FORBIDDEN_SENDER_ACTIONS: FrozenSet[str] = frozenset({
    "issue_title_edit",
    "pull_request_title_edit",
    "release_title_edit",
    "label_name_edit",
    "milestone_title_edit",
    "repository_rename",
    "issue_transfer",
    "pull_request_transfer",
})

ALLOWED_SENDER_ACTIONS: FrozenSet[str] = frozenset({
    "issue_body_edit",
    "issue_label_modify",
    "issue_assignee_modify",
    "issue_state_change",
    "pull_request_body_edit",
    "pull_request_label_modify",
    "pull_request_assignee_modify",
    "pull_request_state_change",
    "issue_comment_create",
    "issue_comment_edit",
    "pull_request_comment_create",
    "pull_request_comment_edit",
    "pull_request_review_comment_create",
    "pull_request_review_comment_reply",
    "commit_comment_create",
    "commit_comment_edit",
    "git_tag_description_edit",
    "git_tag_assets_upload",
    "label_description_edit",
    "milestone_description_edit",
    "milestone_due_date_edit",
})

OUT_OF_SCOPE_ACTIONS: FrozenSet[str] = frozenset({
    "issue_create",
    "pull_request_create",
    "commit_create",
    "git_tag_create",
    "label_create",
    "milestone_create",
    "issue_delete",
    "pull_request_delete",
    "commit_delete",
    "git_tag_delete",
    "label_delete",
    "milestone_delete",
    "repository_rename",
    "repository_transfer",
    "issue_transfer",
    "history_rewrite",
})


# -------------------------
# Optional: GitHub event -> artifact class names
# (ONLY if you actually ingest GitHub Events elsewhere)
# -------------------------

GITHUB_EVENT_TO_ARTIFACT_CLASS: Dict[str, str] = {
    "IssuesEvent": "Issue",
    "PullRequestEvent": "PullRequest",
    "PushEvent": "Commit",
    "CreateEvent": "Commit",
    "IssueCommentEvent": "IssueComment",
    "PullRequestReviewEvent": "PullRequestComment",
    "PullRequestReviewCommentEvent": "PullRequestComment",
    "CommitCommentEvent": "CommitComment",
}

ROUTING_NAMESPACE: FrozenSet[str] = frozenset(GITHUB_EVENT_TO_ARTIFACT_CLASS.keys())
