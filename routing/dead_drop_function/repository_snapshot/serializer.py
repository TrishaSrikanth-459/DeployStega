"""
serializer.py

Serialization utilities for repository snapshots.

Responsibilities:
- Serialize a RepositorySnapshot to disk (JSON)
- Deserialize a RepositorySnapshot from disk
- Preserve identifier ordering and integrity

Non-responsibilities:
- No enumeration
- No validation logic (handled by snapshot.py)
- No URL construction
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
    """
    Serialize a RepositorySnapshot to a JSON file.

    Output format:
    {
      "artifacts": {
        "Issue": [
          {"artifactClass": "Issue", "identifier": [...]},
          ...
        ],
        ...
      }
    }
    """
    data: Dict[str, Any] = {"artifacts": {}}

    # Deterministic class ordering: Enum definition order
    for artifact_class in snapshot.artifact_classes():
        entries: List[Dict[str, Any]] = []
        for artifact in snapshot.artifacts_of(artifact_class):
            entries.append(
                {
                    "artifactClass": artifact_class.name,
                    "identifier": list(artifact.identifier),
                }
            )
        data["artifacts"][artifact_class.name] = entries

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ============================================================
# Deserialization
# ============================================================

def read_snapshot(path: str) -> RepositorySnapshot:
    """
    Load a RepositorySnapshot from a JSON file produced by write_snapshot().

    Structural integrity is enforced here; semantic validity is enforced in snapshot.py
    when you build from enumeration. For runtime reads, we assume the file is already
    canonical (since you produced it with write_snapshot()).
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    raw_artifacts = raw.get("artifacts")
    if not isinstance(raw_artifacts, dict):
        raise SnapshotError("Invalid snapshot format: missing or invalid 'artifacts'")

    artifacts: Dict[ArtifactClass, List[SnapshotArtifact]] = {}

    for class_name in sorted(raw_artifacts.keys()):
        entries = raw_artifacts[class_name]

        try:
            artifact_class = ArtifactClass[class_name]
        except KeyError as e:
            raise SnapshotError(f"Unknown artifact class in snapshot: {class_name}") from e

        if not isinstance(entries, list):
            raise SnapshotError(f"Invalid entries for artifact class {class_name}: expected list")

        bucket: List[SnapshotArtifact] = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise SnapshotError(f"Invalid artifact entry for {class_name}: expected object")
            if "identifier" not in entry:
                raise SnapshotError(f"Missing identifier for artifact class {class_name}")

            identifier = entry["identifier"]
            if not isinstance(identifier, list):
                raise SnapshotError(f"Identifier must be a list for artifact class {class_name}")

            bucket.append(SnapshotArtifact(artifact_class=artifact_class, identifier=tuple(identifier)))

        artifacts[artifact_class] = bucket

    return RepositorySnapshot(artifacts={k: tuple(v) for k, v in artifacts.items()})
