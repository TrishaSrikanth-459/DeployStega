"""
serializer.py

Serialization utilities for repository snapshots.
"""

from __future__ import annotations

import json
from typing import Dict, Any, List

from .snapshot import RepositorySnapshot, SnapshotArtifact, SnapshotError
from .schema import ArtifactClass


# ============================================================
# Serialization
# ============================================================

def write_snapshot(snapshot: RepositorySnapshot, path: str) -> None:
    data: Dict[str, Any] = {"artifacts": {}}

    for artifact_class in snapshot.artifact_classes():
        data["artifacts"][artifact_class.name] = [
            {
                "artifactClass": artifact_class.name,
                "identifier": list(artifact.identifier),
            }
            for artifact in snapshot.artifacts_of(artifact_class)
        ]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ============================================================
# Deserialization
# ============================================================

def read_snapshot(path: str) -> RepositorySnapshot:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    raw_artifacts = raw.get("artifacts")
    if not isinstance(raw_artifacts, dict):
        raise SnapshotError("Invalid snapshot: missing 'artifacts'")

    artifacts: Dict[ArtifactClass, List[SnapshotArtifact]] = {}

    for class_name, entries in raw_artifacts.items():
        try:
            artifact_class = ArtifactClass[class_name]
        except KeyError as e:
            raise SnapshotError(f"Unknown artifact class: {class_name}") from e

        if not isinstance(entries, list):
            raise SnapshotError(f"Invalid entries for {class_name}")

        artifacts[artifact_class] = [
            SnapshotArtifact(
                artifact_class=artifact_class,
                identifier=tuple(entry["identifier"]),
            )
            for entry in entries
        ]

    return RepositorySnapshot(
        artifacts={k: tuple(v) for k, v in artifacts.items()}
    )

