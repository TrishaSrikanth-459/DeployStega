"""
schema.py

Structural schemas for GitHub artifact identifiers,
exactly as defined in the DeployStega routing namespace.

This module defines:
- Artifact classes (canonical, singular)
- Ordered identifier fields per artifact
- No addressability logic
- No behavior
- No snapshot acquisition
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Dict


# =========================
# Artifact Classes
# =========================

class ArtifactClass(Enum):
    """
    Canonical routing namespace artifact classes.

    IMPORTANT:
    - Enum *names* are the canonical class names (and snapshot schema keys)
    - Enum *values* are descriptive only
    - Names are singular by design
    """

    Repository = "repository"

    Issue = "issue"
    IssueComment = "issue_comment"

    PullRequest = "pull_request"
    PullRequestComment = "pull_request_comment"

    Commit = "commit"
    CommitComment = "commit_comment"


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
# Canonical Schemas (URL-faithful)
# =========================

REPOSITORY_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.Repository,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
    ),
)

ISSUE_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.Issue,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("issue_number", "integer"),
    ),
)

ISSUE_COMMENT_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.IssueComment,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("issue_number", "integer"),
    ),
)

PULL_REQUEST_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.PullRequest,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("pull_number", "integer"),
    ),
)

PULL_REQUEST_COMMENT_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.PullRequestComment,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("pull_number", "integer"),
    ),
)

COMMIT_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.Commit,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("commit_sha", "hash"),
    ),
)

COMMIT_COMMENT_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.CommitComment,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("commit_sha", "hash"),
    ),
)


# =========================
# Schema Registry
# =========================

SCHEMA_REGISTRY: Dict[ArtifactClass, ArtifactIdentifierSchema] = {
    ArtifactClass.Repository: REPOSITORY_SCHEMA,

    ArtifactClass.Issue: ISSUE_SCHEMA,
    ArtifactClass.IssueComment: ISSUE_COMMENT_SCHEMA,

    ArtifactClass.PullRequest: PULL_REQUEST_SCHEMA,
    ArtifactClass.PullRequestComment: PULL_REQUEST_COMMENT_SCHEMA,

    ArtifactClass.Commit: COMMIT_SCHEMA,
    ArtifactClass.CommitComment: COMMIT_COMMENT_SCHEMA,
}


def get_schema(artifact_class: ArtifactClass) -> ArtifactIdentifierSchema:
    """
    Retrieve the canonical identifier schema for an artifact class.
    """
    try:
        return SCHEMA_REGISTRY[artifact_class]
    except KeyError as e:
        raise KeyError(
            f"No identifier schema registered for artifact class: {artifact_class}"
        ) from e
