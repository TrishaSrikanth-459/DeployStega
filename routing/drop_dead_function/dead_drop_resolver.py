"""
dead_drop_resolver.py

Deterministic dead-drop resolver over a fixed repository snapshot.

Responsibilities:
- Deterministically map shared inputs to:
    - an artifact class
    - an existing identifier tuple from the snapshot
    - a role-appropriate GitHub URL
- Maintain sender/receiver synchronization
- Operate entirely offline

Non-responsibilities:
- No enumeration or API access
- No behavioral feasibility filtering
- No timing or scheduling logic
- No payload encoding or decoding
"""

from __future__ import annotations

import hashlib
from typing import Tuple, Any, List

from schema import ArtifactClass
from snapshot import RepositorySnapshot
from serializer import read_snapshot
from github_url_builder import GitHubURLBuilder, Role  # assumes file name
# If the builder lives in a different file, adjust the import accordingly.


# ============================================================
# Resolver Errors
# ============================================================

class ResolutionError(Exception):
    """Raised when deterministic resolution fails."""


# ============================================================
# Dead-Drop Resolver
# ============================================================

class DeadDropResolver:
    """
    Deterministic resolver mapping shared inputs to a GitHub URL.
    """

    def __init__(self, snapshot: RepositorySnapshot):
        self.snapshot = snapshot

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def resolve(
        self,
        *,
        epoch: int,
        sender_id: str,
        receiver_id: str,
        role: Role,
        owner: str,
        repo: str,
    ) -> Tuple[ArtifactClass, Tuple[Any, ...], str]:
        """
        Resolve a dead-drop location.

        Returns:
            (artifact_class, identifier_tuple, selected_url)
        """
        digest = self._digest(epoch, sender_id, receiver_id)

        artifact_class = self._select_artifact_class(digest)
        identifier = self._select_identifier(artifact_class, digest)

        url_builder = GitHubURLBuilder(owner=owner, repo=repo)
        urls = url_builder.urls_for(
            artifact_class=self._artifact_class_str(artifact_class),
            identifier=identifier,
            role=role,
        )

        if not urls:
            raise ResolutionError("No URLs returned for resolved artifact")

        # Deterministically select one URL if multiple are available
        url_index = self._slice(digest, 2) % len(urls)
        url = urls[url_index]

        return artifact_class, identifier, url

    # --------------------------------------------------------
    # Deterministic selection
    # --------------------------------------------------------

    def _digest(self, epoch: int, sender_id: str, receiver_id: str) -> bytes:
        """
        Compute shared deterministic digest.
        """
        h = hashlib.sha256()
        h.update(str(epoch).encode())
        h.update(sender_id.encode())
        h.update(receiver_id.encode())
        return h.digest()

    def _select_artifact_class(self, digest: bytes) -> ArtifactClass:
        """
        Select artifact class from snapshot namespace.
        """
        classes = list(self.snapshot.artifact_classes())
        if not classes:
            raise ResolutionError("Snapshot contains no artifact classes")

        idx = self._slice(digest, 0) % len(classes)
        return classes[idx]

    def _select_identifier(
        self,
        artifact_class: ArtifactClass,
        digest: bytes,
    ) -> Tuple[Any, ...]:
        """
        Select an identifier tuple from the snapshot for the given class.
        """
        artifacts = self.snapshot.artifacts_of(artifact_class)
        if not artifacts:
            raise ResolutionError(f"No artifacts for class {artifact_class}")

        idx = self._slice(digest, 1) % len(artifacts)
        return artifacts[idx].identifier

    # --------------------------------------------------------
    # Helpers
    # --------------------------------------------------------

    @staticmethod
    def _slice(digest: bytes, i: int, width: int = 8) -> int:
        """
        Deterministically slice the digest.
        """
        start = i * width
        end = start + width
        return int.from_bytes(digest[start:end], "big")

    @staticmethod
    def _artifact_class_str(artifact_class: ArtifactClass) -> str:
        """
        Convert ArtifactClass enum to URL-builder key.
        """
        mapping = {
            ArtifactClass.REPOSITORY: "Repository",
            ArtifactClass.ISSUE: "Issue",
            ArtifactClass.PULL_REQUEST: "PullRequest",
            ArtifactClass.COMMIT: "Commit",
            ArtifactClass.ISSUE_COMMENT: "IssueComment",
            ArtifactClass.PULL_REQUEST_COMMENT: "PullRequestComment",
            ArtifactClass.COMMIT_COMMENT: "CommitComment",
        }
        return mapping[artifact_class]


# ============================================================
# Convenience Loader
# ============================================================

def load_resolver(snapshot_path: str) -> DeadDropResolver:
    """
    Load a resolver from a serialized snapshot file.
    """
    snapshot = read_snapshot(snapshot_path)
    return DeadDropResolver(snapshot)

