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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Iterable, Any, Mapping
from collections import defaultdict

from .schema import (
    ArtifactClass,
    ArtifactIdentifierSchema,
    IdentifierField,
    get_schema,
)

# ============================================================
# Exceptions
# ============================================================

class SnapshotError(Exception):
    """Base class for snapshot-related errors."""

    def __init__(self, message: str, *, context: Dict[str, Any] | None = None):
        super().__init__(message)
        self.context = context or {}

    def __str__(self) -> str:
        if not self.context:
            return self.args[0]
        return f"{self.args[0]} | context={self.context}"


class SchemaViolation(SnapshotError):
    """Raised when an identifier violates its schema."""

    def __init__(
        self,
        message: str,
        *,
        artifact_class: ArtifactClass | None = None,
        field_name: str | None = None,
        expected_type: str | None = None,
        actual_value: Any | None = None,
    ):
        ctx = {
            "artifact_class": artifact_class,
            "field": field_name,
            "expected_type": expected_type,
            "actual_value": actual_value,
        }
        super().__init__(message, context={k: v for k, v in ctx.items() if v is not None})


class DuplicateIdentifier(SnapshotError):
    """Raised when duplicate identifiers are detected."""

    def __init__(
        self,
        message: str,
        *,
        artifact_class: ArtifactClass,
        identifier: Tuple[Any, ...],
    ):
        super().__init__(
            message,
            context={
                "artifact_class": artifact_class,
                "identifier": identifier,
            },
        )


class UnknownArtifactClass(SnapshotError):
    """Raised when an unknown artifact class string is encountered."""

    def __init__(self, raw: str):
        super().__init__(
            f"Unknown artifact class '{raw}'",
            context={"raw_class": raw},
        )


# ============================================================
# Helpers
# ============================================================

def _coerce_field(value: Any, field: IdentifierField) -> Any:
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
    values: List[Any] = []

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
# Snapshot Objects
# ============================================================

@dataclass(frozen=True)
class SnapshotArtifact:
    artifact_class: ArtifactClass
    identifier: Tuple[Any, ...]


@dataclass
class RepositorySnapshot:
    """
    Canonical, immutable snapshot of repository artifacts.
    """

    artifacts: Dict[ArtifactClass, Tuple[SnapshotArtifact, ...]] = field(
        default_factory=dict
    )

    # --------------------------------------------------------
    # Construction
    # --------------------------------------------------------

    @classmethod
    def from_enumeration(cls, raw_snapshot: Dict[str, Any]) -> "RepositorySnapshot":
        raw_artifacts = raw_snapshot.get("artifacts")
        if raw_artifacts is None:
            raise SnapshotError("Missing 'artifacts' section in snapshot")

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
                    SnapshotArtifact(artifact_class, identifier)
                )

        frozen = {
            cls_: tuple(sorted(items, key=lambda a: a.identifier))
            for cls_, items in buckets.items()
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
