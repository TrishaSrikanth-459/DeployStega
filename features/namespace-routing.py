"""
Routing namespace and identifier schemas for DeployStega.
"""

from typing import FrozenSet, Dict, Tuple
from dataclasses import dataclass
from enum import Enum

# Artifact Classes

class ArtifactClass(Enum):
    REPOSITORY = "Repository"
    ISSUE = "Issue"
    PULL_REQUEST = "PullRequest"
    COMMIT = "Commit"
    ISSUE_COMMENT = "IssueComment"
    PULL_REQUEST_COMMENT = "PullRequestComment"
    COMMIT_COMMENT = "CommitComment"
    GIT_TAG = "GitTag"
    LABEL = "Label"
    MILESTONE = "Milestone"


ARTIFACT_CLASSES: FrozenSet[str] = frozenset({
    ArtifactClass.REPOSITORY.value,
    ArtifactClass.ISSUE.value,
    ArtifactClass.PULL_REQUEST.value,
    ArtifactClass.COMMIT.value,
    ArtifactClass.ISSUE_COMMENT.value,
    ArtifactClass.PULL_REQUEST_COMMENT.value,
    ArtifactClass.COMMIT_COMMENT.value,
    ArtifactClass.GIT_TAG.value,
    ArtifactClass.LABEL.value,
    ArtifactClass.MILESTONE.value
})

# Identifier Schemas

@dataclass(frozen=True)
class IdentifierSchema:
    fields: Tuple[str, ...]


IDENTIFIER_SCHEMAS: Dict[str, IdentifierSchema] = {
    "Repository": IdentifierSchema(("owner", "repo")),
    "Issue": IdentifierSchema(("owner", "repo", "issue_number")),
    "PullRequest": IdentifierSchema(("owner", "repo", "pull_number")),
    "Commit": IdentifierSchema(("owner", "repo", "branch", "commit_sha")),
    "IssueComment": IdentifierSchema(("owner", "repo", "issue_number")),
    "PullRequestComment": IdentifierSchema(("owner", "repo", "pull_number")),
    "CommitComment": IdentifierSchema(("owner", "repo", "commit_sha")),
    "GitTag": IdentifierSchema(("owner", "repo", "tag")),
    "Label": IdentifierSchema(("owner", "repo", "label_name")),
    "Milestone": IdentifierSchema(("owner", "repo", "milestone_number"))
}

# GitHub Event Mapping (for feature extraction)

GITHUB_EVENT_TO_ARTIFACT_CLASS: Dict[str, str] = {
    'IssuesEvent': 'Issue',
    'PullRequestEvent': 'PullRequest',
    'PushEvent': 'Commit',
    'CreateEvent': 'Commit',
    'IssueCommentEvent': 'IssueComment',
    'PullRequestReviewEvent': 'PullRequestComment',
    'PullRequestReviewCommentEvent': 'PullRequestComment',
    'CommitCommentEvent': 'CommitComment'
}

ROUTING_NAMESPACE: FrozenSet[str] = frozenset(GITHUB_EVENT_TO_ARTIFACT_CLASS.keys())

# Roles

class Role(Enum):
    SENDER = "sender"
    RECEIVER = "receiver"

# Identifier-Preserving Constraints - Fields that define identifiers (must NOT be modified)
IDENTIFIER_DEFINING_FIELDS: Dict[str, FrozenSet[str]] = {
    "Issue": frozenset({"issue_number"}),
    "PullRequest": frozenset({"pull_number"}),
    "Commit": frozenset({"commit_sha", "branch"}),
    "IssueComment": frozenset({"issue_number"}),
    "PullRequestComment": frozenset({"pull_number"}),
    "CommitComment": frozenset({"commit_sha"}),
    "GitTag": frozenset({"tag"}),
    "Label": frozenset({"label_name"}),
    "Milestone": frozenset({"milestone_number"}),
    "Repository": frozenset({"owner", "repo"})
}

# Forbidden sender actions (high-salience, identifier-changing)
FORBIDDEN_SENDER_ACTIONS: FrozenSet[str] = frozenset({
    'issue_title_edit',
    'pull_request_title_edit',
    'release_title_edit',
    'label_name_edit',
    'milestone_title_edit',
    'repository_rename',
    'issue_transfer',
    'pull_request_transfer'
})

# Allowed sender actions (identifier-preserving only)
ALLOWED_SENDER_ACTIONS: FrozenSet[str] = frozenset({
    'issue_body_edit',
    'issue_label_modify',
    'issue_assignee_modify',
    'issue_state_change',
    'pull_request_body_edit',
    'pull_request_label_modify',
    'pull_request_assignee_modify',
    'pull_request_state_change',
    'issue_comment_create',
    'issue_comment_edit',
    'pull_request_comment_create',
    'pull_request_comment_edit',
    'pull_request_review_comment_create',
    'pull_request_review_comment_reply',
    'commit_comment_create',
    'commit_comment_edit',
    'git_tag_description_edit',
    'git_tag_assets_upload',
    'label_description_edit',
    'milestone_description_edit',
    'milestone_due_date_edit'
})

# Out-of-scope actions 
OUT_OF_SCOPE_ACTIONS: FrozenSet[str] = frozenset({
    'issue_create',
    'pull_request_create',
    'commit_create',
    'git_tag_create',
    'label_create',
    'milestone_create',
    'issue_delete',
    'pull_request_delete',
    'commit_delete',
    'git_tag_delete',
    'label_delete',
    'milestone_delete',
    'repository_rename',
    'repository_transfer',
    'issue_transfer',
    'history_rewrite'
})

# URL Patterns

WEB_URL_PATTERNS: Dict[str, str] = {
    "Repository": "https://github.com/{owner}/{repo}",
    "Issue": "https://github.com/{owner}/{repo}/issues/{issue_number}",
    "PullRequest": "https://github.com/{owner}/{repo}/pull/{pull_number}",
    "Commit": "https://github.com/{owner}/{repo}/commit/{commit_sha}",
    "IssueComment": "https://github.com/{owner}/{repo}/issues/{issue_number}",
    "PullRequestComment": "https://github.com/{owner}/{repo}/pull/{pull_number}/files",
    "CommitComment": "https://github.com/{owner}/{repo}/commit/{commit_sha}",
    "GitTag": "https://github.com/{owner}/{repo}/releases/tag/{tag}",
    "Label": "https://github.com/{owner}/{repo}/labels",
    "Milestone": "https://github.com/{owner}/{repo}/milestone/{milestone_number}"
}

# Feature Extraction Configuration

SESSION_TIMEOUT_SECONDS: int = 1800
MIN_EVENTS_PER_USER: int = 5
MIN_TIMING_DELTA_SECONDS: float = 1.0
MAX_TIMING_DELTA_SECONDS: float = 86400.0

# Data Source Configuration

DATA_YEAR: int = 2025
DATA_MONTH: int = 9
DATA_START_DAY: int = 1
DATA_END_DAY: int = 30

# Output Configuration

OUTPUT_JSON_PATH: str = "behavioral_priors.json"
OUTPUT_FIGURES_DIR: str = "figures"
