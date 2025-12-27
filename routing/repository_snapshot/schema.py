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
    REPOSITORY = "repository"
    ISSUE = "issue"
    PULL_REQUEST = "pull_request"
    COMMIT = "commit"
    ISSUE_COMMENT = "issue_comment"
    PULL_REQUEST_COMMENT = "pull_request_comment"
    COMMIT_COMMENT = "commit_comment"


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
# Canonical Schemas (Exact)
# =========================

REPOSITORY_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.REPOSITORY,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
    ),
)

ISSUE_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.ISSUE,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("issue_number", "integer"),
    ),
)

PULL_REQUEST_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.PULL_REQUEST,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("pull_number", "integer"),
        IdentifierField("branch_1", "string"),
        IdentifierField("branch_2", "string"),
    ),
)

COMMIT_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.COMMIT,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("branch", "string"),
        IdentifierField("path", "string"),
        IdentifierField("commit_sha", "hash"),
    ),
)

ISSUE_COMMENT_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.ISSUE_COMMENT,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("issue_number", "integer"),
    ),
)

PULL_REQUEST_COMMENT_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.PULL_REQUEST_COMMENT,
    fields=(
        IdentifierField("owner", "string"),
        IdentifierField("repo", "string"),
        IdentifierField("pull_number", "integer"),
    ),
)

COMMIT_COMMENT_SCHEMA = ArtifactIdentifierSchema(
    artifact_class=ArtifactClass.COMMIT_COMMENT,
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
    schema.artifact_class: schema
    for schema in (
        REPOSITORY_SCHEMA,
        ISSUE_SCHEMA,
        PULL_REQUEST_SCHEMA,
        COMMIT_SCHEMA,
        ISSUE_COMMENT_SCHEMA,
        PULL_REQUEST_COMMENT_SCHEMA,
        COMMIT_COMMENT_SCHEMA,
    )
}


def get_schema(artifact_class: ArtifactClass) -> ArtifactIdentifierSchema:
    """
    Retrieve the canonical identifier schema for an artifact class.
    """
    return SCHEMA_REGISTRY[artifact_class]
