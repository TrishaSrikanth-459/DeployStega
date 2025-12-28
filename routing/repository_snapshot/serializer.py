"""
serializer.py

Snapshot serialization and deserialization.

This module:
- Serializes a validated RepositorySnapshot to disk
- Deserializes a snapshot back into a RepositorySnapshot
- Guarantees lossless, deterministic round-trip behavior

This module performs:
- No enumeration
- No schema validation
- No network access
- No behavioral logic

It is the persistence boundary for repository snapshots.
"""

from __future__ import annotations

import json
from typing import Dict, Any, List

from snapshot import RepositorySnapshot, SnapshotArtifact, SnapshotError
from schema import ArtifactClass


# ============================================================
# Exceptions
# ============================================================

class SerializationError(SnapshotError):
    """Raised when snapshot serialization or deserialization fails."""


# ============================================================
# Helpers
# ============================================================

def _artifact_class_to_str(artifact_class: ArtifactClass) -> str:
    return artifact_class.value


def _artifact_class_from_str(value: str) -> ArtifactClass:
    try:
        return ArtifactClass(value)
    except ValueError:
        raise SerializationError(
            f"Unknown artifact class during deserialization: '{value}'",
            context={"artifact_class": value},
        )


# ============================================================
# Serialization
# ============================================================

def serialize_snapshot(snapshot: RepositorySnapshot) -> Dict[str, Any]:
    """
    Convert a RepositorySnapshot into a JSON-serializable dictionary.

    This function assumes the snapshot is already schema-valid.
    """
    artifacts: Dict[str, List[List[Any]]] = {}

    for artifact_class, entries in snapshot.artifacts.items():
        key = _artifact_class_to_str(artifact_class)
        artifacts[key] = [list(a.identifier) for a in entries]

    return {
        "artifacts": artifacts,
    }


def write_snapshot(snapshot: RepositorySnapshot, path: str) -> None:
    """
    Write a RepositorySnapshot to disk as JSON.
    """
    try:
        payload = serialize_snapshot(snapshot)
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        raise SerializationError(
            "Failed to write snapshot",
            context={"path": path, "error": str(e)},
        )


# ============================================================
# Deserialization
# ============================================================

def deserialize_snapshot(data: Dict[str, Any]) -> RepositorySnapshot:
    """
    Reconstruct a RepositorySnapshot from serialized data.

    This assumes the data was produced by serialize_snapshot().
    """
    try:
        raw_artifacts: Dict[str, Any] = data.get("artifacts", {})
        buckets = {}

        for raw_class, identifiers in raw_artifacts.items():
            artifact_class = _artifact_class_from_str(raw_class)
            entries = tuple(
                SnapshotArtifact(
                    artifact_class=artifact_class,
                    identifier=tuple(identifier),
                )
                for identifier in identifiers
            )
            buckets[artifact_class] = entries

        return RepositorySnapshot(artifacts=buckets)

    except Exception as e:
        raise SerializationError(
            "Failed to deserialize snapshot",
            context={"error": str(e)},
        )


def read_snapshot(path: str) -> RepositorySnapshot:
    """
    Read a RepositorySnapshot from disk.
    """
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return deserialize_snapshot(data)
    except Exception as e:
        raise SerializationError(
            "Failed to read snapshot",
            context={"path": path, "error": str(e)},
        )
