from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Dict


# =========================
# Artifact Classes (ROUTING ONLY)
# =========================

class ArtifactClass(Enum):
    """
    Canonical routing namespace artifact classes.

    IMPORTANT:
    - This enum MUST contain ONLY routing (dead-drop) artifact classes.
    - Benign interaction classes MUST NOT appear here.
    """

    Repository = "repository"
    Issue = "issue"
    IssueComment = "issue_comment"
    PullRequest = "pull_request"
    PullRequestComment = "pull_request_comment"
    Commit = "commit"
    CommitComment = "commit_comment"
    GitTag = "git_tag"
    Label = "label"
    Milestone = "milestone"


# =========================
# Identifier Field
# =========================

@dataclass(frozen=True)
class IdentifierField:
    name: str
    field_type: str  # "string", "integer", "hash"


# =========================
# Identifier Schema
# =========================

@dataclass(frozen=True)
class ArtifactIdentifierSchema:
    artifact_class: ArtifactClass
    fields: Tuple[IdentifierField, ...]


# =========================
# Canonical Schemas
# =========================

REPOSITORY_SCHEMA = ArtifactIdentifierSchema(
    ArtifactClass.Repository,
    (
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
    ),
)

ISSUE_SCHEMA = ArtifactIdentifierSchema(
    ArtifactClass.Issue,
    (
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("issue_number", "integer"),
    ),
)

ISSUE_COMMENT_SCHEMA = ArtifactIdentifierSchema(
    ArtifactClass.IssueComment,
    (
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("issue_number", "integer"),
    ),
)

PULL_REQUEST_SCHEMA = ArtifactIdentifierSchema(
    ArtifactClass.PullRequest,
    (
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("pull_number", "integer"),
    ),
)

PULL_REQUEST_COMMENT_SCHEMA = ArtifactIdentifierSchema(
    ArtifactClass.PullRequestComment,
    (
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("pull_number", "integer"),
    ),
)

COMMIT_SCHEMA = ArtifactIdentifierSchema(
    ArtifactClass.Commit,
    (
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("commit_sha", "hash"),
    ),
)

COMMIT_COMMENT_SCHEMA = ArtifactIdentifierSchema(
    ArtifactClass.CommitComment,
    (
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("commit_sha", "hash"),
    ),
)

GIT_TAG_SCHEMA = ArtifactIdentifierSchema(
    ArtifactClass.GitTag,
    (
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("tag", "string"),
    ),
)

LABEL_SCHEMA = ArtifactIdentifierSchema(
    ArtifactClass.Label,
    (
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("label_name", "string"),
    ),
)

MILESTONE_SCHEMA = ArtifactIdentifierSchema(
    ArtifactClass.Milestone,
    (
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("milestone_number", "integer"),
    ),
)

SCHEMA_REGISTRY: Dict[ArtifactClass, ArtifactIdentifierSchema] = {
    s.artifact_class: s
    for s in [
        REPOSITORY_SCHEMA,
        ISSUE_SCHEMA,
        ISSUE_COMMENT_SCHEMA,
        PULL_REQUEST_SCHEMA,
        PULL_REQUEST_COMMENT_SCHEMA,
        COMMIT_SCHEMA,
        COMMIT_COMMENT_SCHEMA,
        GIT_TAG_SCHEMA,
        LABEL_SCHEMA,
        MILESTONE_SCHEMA,
    ]
}


def get_schema(artifact_class: ArtifactClass) -> ArtifactIdentifierSchema:
    return SCHEMA_REGISTRY[artifact_class]
