"""
dead_drop_resolver.py

Deterministic dead-drop resolver.

Responsibilities:
- Deterministically select an artifact class
- Deterministically select an identifier within that class
- Deterministically select ONE URL among all valid options for that (class, id, role)
- Enforce feasibility constraints
- Respect snapshot reality (no invented artifacts)
- Deterministically retry when a candidate is infeasible (rehash rule)

Non-responsibilities:
- No network access
- No snapshot construction
- No behavioral learning
"""

from __future__ import annotations

import hashlib
from typing import Dict, Tuple, List, Any, Literal

from .github_url_builder import GitHubURLBuilder
from .feasibility_region import FeasibilityRegion
from .repository_snapshot.snapshot import RepositorySnapshot
from .repository_snapshot.schema import ArtifactClass

Role = Literal["sender", "receiver"]


class DeadDropResolver:
    """
    Deterministic resolver mapping (epoch, sender_id, receiver_id, role)
    to a concrete GitHub URL.
    """

    def __init__(
        self,
        *,
        snapshot: RepositorySnapshot,
        feasibility_region: FeasibilityRegion,
        owner: str,
        repo: str,
        max_rehash_attempts: int = 512,
    ):
        self.snapshot = snapshot
        self.feasibility = feasibility_region
        self.url_builder = GitHubURLBuilder(owner=owner, repo=repo)
        self.max_rehash_attempts = max_rehash_attempts

    # =========================================================
    # Public API
    # =========================================================

    def resolve(
        self,
        *,
        epoch: int,
        sender_id: str,
        receiver_id: str,
        role: str,
    ) -> Dict[str, Any]:
        """
        Resolve a deterministic dead drop.

        Returns exactly one URL.

        IMPORTANT:
        If the initially selected (class, identifier) has no namespace-valid URL
        or no feasible URL under constraints, we apply a deterministic rehash rule
        and retry until we find a valid triple or exhaust max_rehash_attempts.
        """
        role_t = self._validate_role(role)

        if epoch < 0:
            raise ValueError("epoch must be non-negative")

        # -----------------------------------------------------
        # Deterministic retry loop (rehash collision/infeasibility handling)
        # -----------------------------------------------------
        base_material = f"{epoch}|{sender_id}|{receiver_id}"

        for attempt in range(self.max_rehash_attempts):
            # Deterministically vary seed by attempt counter
            d = self._hash_to_int(f"{base_material}|{attempt}")

            # 1) candidate class/id
            artifact_class = self._select_artifact_class(d)
            identifier = self._select_identifier(d, artifact_class)

            # 2) all namespace-valid URL candidates for this role
            urls = self._candidate_urls(artifact_class, identifier, role_t)
            if not urls:
                # Namespace has no valid URLs for this role+identifier (e.g., missing fields)
                continue

            # 3) enforce feasibility constraints (may filter further)
            allowed = self.feasibility.filter_allowed_urls(
                epoch=epoch,
                artifact_class=artifact_class.name,
                role=role_t,
                urls=urls,
            )
            if not allowed:
                # No feasible URLs at this epoch for this role
                continue

            # 4) choose exactly one URL deterministically from allowed set
            url = self._select_one_url(
                epoch=epoch,
                base_seed=d,
                artifact_class=artifact_class,
                identifier=identifier,
                role=role_t,
                allowed_urls=allowed,
            )

            return {
                "artifactClass": artifact_class.name,
                "identifier": identifier,
                "url": url,
            }

        raise RuntimeError(
            f"No routable, namespace-valid, feasible dead drop found after "
            f"{self.max_rehash_attempts} attempts at epoch {epoch}"
        )

    # =========================================================
    # Deterministic helpers
    # =========================================================

    @staticmethod
    def _hash_to_int(s: str) -> int:
        return int(hashlib.sha256(s.encode("utf-8")).hexdigest(), 16)

    @staticmethod
    def _validate_role(role: str) -> Role:
        r = role.strip().lower()
        if r not in ("sender", "receiver"):
            raise ValueError(f"Invalid role: {role}")
        return r  # type: ignore[return-value]

    # ---------------------------------------------------------
    # Artifact class selection (ONLY from non-empty classes)
    # ---------------------------------------------------------

    def _select_artifact_class(self, d: int) -> ArtifactClass:
        available_classes = [
            c for c in self.snapshot.artifact_classes()
            if self.snapshot.artifacts_of(c)
        ]
        if not available_classes:
            raise RuntimeError("Snapshot contains no routable artifacts")

        idx = d % len(available_classes)
        return available_classes[idx]

    # ---------------------------------------------------------
    # Identifier selection
    # ---------------------------------------------------------

    def _select_identifier(
        self,
        d: int,
        artifact_class: ArtifactClass,
    ) -> Tuple:
        artifacts = self.snapshot.artifacts_of(artifact_class)
        if not artifacts:
            raise RuntimeError(f"No artifacts for class {artifact_class.name}")

        idx = d % len(artifacts)
        return artifacts[idx].identifier

    # ---------------------------------------------------------
    # URL candidates (namespace options)
    # ---------------------------------------------------------

    def _candidate_urls(
        self,
        artifact_class: ArtifactClass,
        identifier: Tuple,
        role: Role,
    ) -> List[str]:
        """
        Delegate to the URL builder to expose all namespace-valid URLs
        for the given role.

        Contract:
        - url_builder returns [] if no namespace-valid URL exists for this
          (artifact_class, identifier, role).
        """
        urls = self.url_builder.urls_for(
            artifact_class.name,
            identifier,
            role,
        )

        # Defensive: normalize & drop empties
        return [u.strip() for u in urls if isinstance(u, str) and u.strip()]

    # ---------------------------------------------------------
    # Deterministic one-URL selection
    # ---------------------------------------------------------

    def _select_one_url(
        self,
        *,
        epoch: int,
        base_seed: int,
        artifact_class: ArtifactClass,
        identifier: Tuple,
        role: Role,
        allowed_urls: List[str],
    ) -> str:
        """
        Choose exactly one URL from allowed_urls deterministically.

        Mix in (epoch, class, role, identifier) so selection is stable but
        sensitive to the exact resolved route.
        """
        id_material = "|".join(str(x) for x in identifier)
        mix = f"{base_seed}|{epoch}|{artifact_class.name}|{role}|{id_material}"
        h = self._hash_to_int(mix)
        idx = h % len(allowed_urls)
        return allowed_urls[idx]
