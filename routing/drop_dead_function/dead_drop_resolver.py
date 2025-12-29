"""
dead_drop_resolver.py

Deterministic Dead-Drop Resolver (Runtime)

Implements the deterministic routing function described in
dead_drop_resolver.md.
"""

from __future__ import annotations

import hashlib
from typing import Tuple, Any, Literal

# ============================================================
# Package-relative imports (CORRECT)
# ============================================================

from .repository_snapshot.snapshot import RepositorySnapshot
from .repository_snapshot.schema import ArtifactClass
from .repository_snapshot.serializer import read_snapshot

from .feasibility_region import FeasibilityRegion
from .github_url_builder import GitHubURLBuilder

Role = Literal["sender", "receiver"]


# ============================================================
# Resolver
# ============================================================

class DeadDropResolver:
    """
    Deterministic dead-drop resolver.

    Constructed offline with:
    - a fixed RepositorySnapshot
    - a feasibility region

    Evaluated at runtime using only shared inputs.
    """

    def __init__(
        self,
        *,
        snapshot: RepositorySnapshot,
        feasibility_region: FeasibilityRegion,
        owner: str,
        repo: str,
    ):
        self.snapshot = snapshot
        self.feasibility = feasibility_region
        self.url_builder = GitHubURLBuilder(owner=owner, repo=repo)

        # Fixed artifact-class namespace
        self.namespace = tuple(self.snapshot.artifact_classes())
        if not self.namespace:
            raise ValueError("Snapshot contains no artifact classes")

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
    ) -> dict[str, Any]:
        """
        Resolve a dead-drop route for a given epoch and role.

        Returns:
            {
                "artifactClass": str,
                "identifier": tuple,
                "url": str,
            }
        """

        digest = self._digest(epoch, sender_id, receiver_id)

        counter = 0
        while True:
            d = self._rehash(digest, counter)

            artifact_class = self._select_artifact_class(d)
            identifier = self._select_identifier(d, artifact_class)
            url = self._select_url(epoch, artifact_class, identifier, role)

            if url is not None:
                return {
                    "artifactClass": artifact_class.name,
                    "identifier": identifier,
                    "url": url,
                }

            counter += 1

    # --------------------------------------------------------
    # Deterministic core
    # --------------------------------------------------------

    @staticmethod
    def _digest(epoch: int, sender: str, receiver: str) -> bytes:
        h = hashlib.sha256()
        h.update(str(epoch).encode("utf-8"))
        h.update(sender.encode("utf-8"))
        h.update(receiver.encode("utf-8"))
        return h.digest()

    @staticmethod
    def _rehash(digest: bytes, counter: int) -> bytes:
        if counter == 0:
            return digest
        h = hashlib.sha256()
        h.update(digest)
        h.update(counter.to_bytes(4, "big"))
        return h.digest()

    # --------------------------------------------------------
    # Artifact selection
    # --------------------------------------------------------

    def _select_artifact_class(self, digest: bytes) -> ArtifactClass:
        idx = int.from_bytes(digest[0:8], "big") % len(self.namespace)
        return self.namespace[idx]

    def _select_identifier(
        self,
        digest: bytes,
        artifact_class: ArtifactClass,
    ) -> Tuple[Any, ...]:

        artifacts = self.snapshot.artifacts_of(artifact_class)
        if not artifacts:
            raise RuntimeError(f"No artifacts for class {artifact_class.name}")

        idx = int.from_bytes(digest[8:16], "big") % len(artifacts)
        return artifacts[idx].identifier

    # --------------------------------------------------------
    # URL selection under feasibility
    # --------------------------------------------------------

    def _select_url(
        self,
        epoch: int,
        artifact_class: ArtifactClass,
        identifier: Tuple[Any, ...],
        role: Role,
    ) -> str | None:
        """
        Select the first feasible URL for the artifact and role,
        or return None if none are allowed.
        """

        # CRITICAL FIX:
        # Pass the canonical enum name directly.
        # DO NOT apply string transformations.
        urls = self.url_builder.urls_for(
            artifact_class.name,
            identifier,
            role,
        )

        for url in urls:
            if self.feasibility.is_url_allowed(
                epoch=epoch,
                artifact_class=artifact_class.name,
                role=role,
                url=url,
            ):
                return url

        return None
