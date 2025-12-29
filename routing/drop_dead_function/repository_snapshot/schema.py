"""
schema.py

Structural schemas for GitHub artifact identifiers,
exactly as defined in namespace.md.

This module defines:
- Artifact classes
- Ordered identifier fields per artifact
- No addressability logic
- No behavior
- No snapshot acquisition
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Dict


# =========================
# Artifact Classes
# =========================

class ArtifactClass(Enum):
    """
    IMPORTANT INVARIANT:

    - Enum MEMBER NAMES must exactly match snapshot JSON keys
      because the serializer uses ArtifactClass[class_name]
    - Enum VALUES preserve canonical semantic labels
    """

    Repositories = "repository"
    Issues = "issue"
    PullRequests = "pull_request"
    Commits = "commit"
    IssueComments = "issue_comment"
    PRComments = "pull_request_comment"
    CommitComments = "commit_comment"
    Discussions = "discussion"
    DiscussionComments = "discussion_comment"


# =========================
# Identifier Field
# =========================

@dataclass(frozen=True)
class IdentifierField:
    """
    A single identifier field in an artifact identifier tuple.
    """
    name: str
    field_type: str  # "string", "integer", "hash"


# =========================
# Identifier Schema
# =========================

@dataclass(frozen=True)
class ArtifactIdentifierSchema:
    """
    Ordered identifier schema for a GitHub artifact class.
    """
    artifact_class: ArtifactClass
    fields: Tuple[IdentifierField, ...]


# =========================
# Canonical Schemas
# =========================

REPOSITORY_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.Repositories,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
    ),
)

ISSUE_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.Issues,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("issue_number", "integer"),
    ),
)

PULL_REQUEST_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.PullRequests,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("pull_number", "integer"),
    ),
)

COMMIT_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.Commits,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("commit_sha", "hash"),
    ),
)

ISSUE_COMMENT_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.IssueComments,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("issue_number", "integer"),
        IdentifierField("comment_id", "integer"),
    ),
)

PULL_REQUEST_COMMENT_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.PRComments,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("pull_number", "integer"),
        IdentifierField("comment_id", "integer"),
    ),
)

COMMIT_COMMENT_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.CommitComments,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("commit_sha", "hash"),
        IdentifierField("comment_id", "integer"),
    ),
)

DISCUSSION_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.Discussions,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("discussion_number", "integer"),
    ),
)

DISCUSSION_COMMENT_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.DiscussionComments,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("discussion_number", "integer"),
        IdentifierField("comment_id", "integer"),
    ),
)


# =========================
# Schema Registry
# =========================

SCHEMA_REGISTRY: Dict[ArtifactClass, ArtifactIdentifierSchema] = {
    schema.artifact_class: schema
    for schema in (
        REPOSITORY_SCHEMA,
        ISSUE_SCHEMA,
        PULL_REQUEST_SCHEMA,
        COMMIT_SCHEMA,
        ISSUE_COMMENT_SCHEMA,
        PULL_REQUEST_COMMENT_SCHEMA,
        COMMIT_COMMENT_SCHEMA,
        DISCUSSION_SCHEMA,
        DISCUSSION_COMMENT_SCHEMA,
    )
}


def get_schema(artifact_class: ArtifactClass) -> ArtifactIdentifierSchema:
    """
    Retrieve the canonical identifier schema for an artifact class.
    """
    return SCHEMA_REGISTRY[artifact_class]
