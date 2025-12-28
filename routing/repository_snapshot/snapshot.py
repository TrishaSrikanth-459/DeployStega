"""
snapshot.py

Canonical repository snapshot representation.

This module:
- Ingests raw enumeration output from enumerators.py
- Validates identifier tuples against schema.py
- Normalizes artifacts into a canonical, immutable snapshot object
- Enforces snapshot-level invariants (uniqueness, schema conformance)

This module performs:
- No enumeration
- No network access
- No serialization
- No behavioral logic

It defines what a repository snapshot *is*.

===========================================================================
USAGE
===========================================================================

Typical workflow:

    from enumerators import build_snapshot
    from snapshot import RepositorySnapshot

    raw = build_snapshot(owner="OWNER", repo="REPO")
    snapshot = RepositorySnapshot.from_enumeration(raw)

The resulting snapshot is:
- Schema-valid
- Deterministically ordered
- Identifier-only (content-blind)
- Ready for serialization or resolver consumption
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Iterable, Any, Mapping
from collections import defaultdict

from schema import (
    ArtifactClass,
    ArtifactIdentifierSchema,
    IdentifierField,
    get_schema,
)

# ============================================================
# Exceptions
# ============================================================

class SnapshotError(Exception):
    """
    Base class for snapshot-related errors.

    All snapshot exceptions carry a message and optional structured context
    to support debugging, reproducibility, and programmatic inspection.
    """

    def __init__(self, message: str, *, context: Dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def __str__(self) -> str:
        if not self.context:
            return self.message
        return f"{self.message} | context={self.context}"


class SchemaViolation(SnapshotError):
    """
    Raised when an identifier tuple violates its declared schema.

    Examples:
    - Missing required field
    - Incorrect field type
    - Malformed identifier value
    """

    def __init__(
        self,
        message: str,
        *,
        artifact_class: ArtifactClass | None = None,
        field_name: str | None = None,
        expected_type: str | None = None,
        actual_value: Any | None = None,
    ):
        context = {
            "artifact_class": artifact_class,
            "field": field_name,
            "expected_type": expected_type,
            "actual_value": actual_value,
        }
        context = {k: v for k, v in context.items() if v is not None}
        super().__init__(message, context=context)


class DuplicateIdentifier(SnapshotError):
    """
    Raised when duplicate canonical identifiers are detected.

    This indicates a violation of snapshot uniqueness invariants.
    """

    def __init__(
        self,
        message: str,
        *,
        artifact_class: ArtifactClass | None = None,
        identifier: Tuple[Any, ...] | None = None,
    ):
        context = {
            "artifact_class": artifact_class,
            "identifier": identifier,
        }
        context = {k: v for k, v in context.items() if v is not None}
        super().__init__(message, context=context)


class UnknownArtifactClass(SnapshotError):
    """
    Raised when an artifact class string from enumeration cannot be mapped
    to a known ArtifactClass enum.
    """

    def __init__(self, raw_class: str):
        super().__init__(
            f"Unknown artifact class '{raw_class}'",
            context={"raw_class": raw_class},
        )


# ============================================================
# Helper functions
# ============================================================

def _coerce_field(value: Any, field: IdentifierField) -> Any:
    """
    Enforce identifier field type constraints.
    """
    if field.field_type == "string":
        if not isinstance(value, str):
            raise SchemaViolation(
                "Field must be string",
                field_name=field.name,
                expected_type="string",
                actual_value=value,
            )
        return value

    if field.field_type == "integer":
        if not isinstance(value, int):
            raise SchemaViolation(
                "Field must be integer",
                field_name=field.name,
                expected_type="integer",
                actual_value=value,
            )
        return value

    if field.field_type == "hash":
        if not isinstance(value, str):
            raise SchemaViolation(
                "Field must be hash string",
                field_name=field.name,
                expected_type="hash",
                actual_value=value,
            )
        return value

    raise SchemaViolation(
        "Unknown identifier field type",
        field_name=field.name,
        expected_type=field.field_type,
    )


def _normalize_identifier(
    raw: Mapping[str, Any],
    schema: ArtifactIdentifierSchema,
) -> Tuple[Any, ...]:
    """
    Convert a raw identifier dict into a canonical ordered tuple
    according to the schema.
    """
    values = []

    for field in schema.fields:
        if field.name not in raw:
            raise SchemaViolation(
                "Missing required identifier field",
                artifact_class=schema.artifact_class,
                field_name=field.name,
            )
        values.append(_coerce_field(raw[field.name], field))

    return tuple(values)


# ============================================================
# Snapshot Data Classes
# ============================================================

@dataclass(frozen=True)
class SnapshotArtifact:
    """
    A single artifact entry in the snapshot.
    """
    artifact_class: ArtifactClass
    identifier: Tuple[Any, ...]


@dataclass
class RepositorySnapshot:
    """
    Canonical snapshot of a repository's addressable artifacts.

    The snapshot is:
    - Schema-valid
    - Duplicate-free
    - Deterministically ordered
    - Content-blind
    """

    artifacts: Dict[ArtifactClass, Tuple[SnapshotArtifact, ...]] = field(
        default_factory=dict
    )

    # --------------------------------------------------------
    # Construction
    # --------------------------------------------------------

    @classmethod
    def from_enumeration(cls, raw_snapshot: Dict[str, Any]) -> "RepositorySnapshot":
        """
        Build a RepositorySnapshot from raw enumeration output
        produced by enumerators.build_snapshot().
        """
        raw_artifacts = raw_snapshot.get("artifacts")
        if raw_artifacts is None:
            raise SnapshotError("Missing 'artifacts' section in raw snapshot")

        buckets: Dict[ArtifactClass, List[SnapshotArtifact]] = defaultdict(list)
        seen: set[Tuple[ArtifactClass, Tuple[Any, ...]]] = set()

        for raw_class, entries in raw_artifacts.items():
            artifact_class = cls._parse_artifact_class(raw_class)
            schema = get_schema(artifact_class)

            for entry in entries:
                raw_id = entry.get("identifierTuple")
                if raw_id is None:
                    raise SchemaViolation(
                        "Missing identifierTuple",
                        artifact_class=artifact_class,
                    )

                identifier = _normalize_identifier(raw_id, schema)
                key = (artifact_class, identifier)

                if key in seen:
                    raise DuplicateIdentifier(
                        "Duplicate identifier detected",
                        artifact_class=artifact_class,
                        identifier=identifier,
                    )

                seen.add(key)
                buckets[artifact_class].append(
                    SnapshotArtifact(
                        artifact_class=artifact_class,
                        identifier=identifier,
                    )
                )

        # Freeze ordering for determinism
        frozen = {
            cls_: tuple(sorted(arts, key=lambda a: a.identifier))
            for cls_, arts in buckets.items()
        }

        return cls(artifacts=frozen)

    # --------------------------------------------------------
    # Accessors
    # --------------------------------------------------------

    def artifact_classes(self) -> Iterable[ArtifactClass]:
        return self.artifacts.keys()

    def artifacts_of(self, artifact_class: ArtifactClass) -> Tuple[SnapshotArtifact, ...]:
        return self.artifacts.get(artifact_class, ())

    def count(self, artifact_class: ArtifactClass) -> int:
        return len(self.artifacts_of(artifact_class))

    # --------------------------------------------------------
    # Internal helpers
    # --------------------------------------------------------

    @staticmethod
    def _parse_artifact_class(raw: str) -> ArtifactClass:
        """
        Convert enumerator artifact class strings into ArtifactClass enum.
        """
        mapping = {
            "Repositories": ArtifactClass.REPOSITORY,
            "Issues": ArtifactClass.ISSUE,
            "PullRequests": ArtifactClass.PULL_REQUEST,
            "Commits": ArtifactClass.COMMIT,
            "IssueComments": ArtifactClass.ISSUE_COMMENT,
            "PRComments": ArtifactClass.PULL_REQUEST_COMMENT,
            "CommitComments": ArtifactClass.COMMIT_COMMENT,
        }

        try:
            return mapping[raw]
        except KeyError:
            raise UnknownArtifactClass(raw)
