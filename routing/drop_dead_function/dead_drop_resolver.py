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
        If the selected (class, identifier) yields no namespace-valid URL
        for the given role, or no feasible URL under constraints,
        a deterministic rehash rule is applied.
        """
        role_t = self._validate_role(role)

        if epoch < 0:
            raise ValueError("epoch must be non-negative")

        base_material = f"{epoch}|{sender_id}|{receiver_id}"

        # -----------------------------------------------------
        # Deterministic retry loop
        # -----------------------------------------------------
        for attempt in range(self.max_rehash_attempts):
            seed = self._hash_to_int(f"{base_material}|{attempt}")

            # 1) Select artifact class (snapshot-only)
            artifact_class = self._select_artifact_class(seed)

            # 2) Select identifier within class (snapshot-only)
            identifier = self._select_identifier(seed, artifact_class)

            # 3) Namespace-valid URL candidates for this role
            urls = self._candidate_urls(
                artifact_class=artifact_class,
                identifier=identifier,
                role=role_t,
            )

            # Namespace rule: some classes have zero sender surfaces
            if not urls:
                continue

            # 4) Enforce feasibility constraints
            allowed = self.feasibility.filter_allowed_urls(
                epoch=epoch,
                artifact_class=artifact_class.name,
                role=role_t,
                urls=urls,
            )

            if not allowed:
                continue

            # 5) Deterministically select exactly one URL
            url = self._select_one_url(
                epoch=epoch,
                base_seed=seed,
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
    # Artifact class selection (snapshot-pure)
    # ---------------------------------------------------------

    def _select_artifact_class(self, seed: int) -> ArtifactClass:
        classes = [
            c for c in self.snapshot.artifact_classes()
            if self.snapshot.artifacts_of(c)
        ]

        if not classes:
            raise RuntimeError("Snapshot contains no routable artifacts")

        return classes[seed % len(classes)]

    # ---------------------------------------------------------
    # Identifier selection (snapshot-pure)
    # ---------------------------------------------------------

    def _select_identifier(
        self,
        seed: int,
        artifact_class: ArtifactClass,
    ) -> Tuple:
        artifacts = self.snapshot.artifacts_of(artifact_class)
        if not artifacts:
            raise RuntimeError(f"No artifacts for class {artifact_class.name}")

        return artifacts[seed % len(artifacts)].identifier

    # ---------------------------------------------------------
    # URL candidates (namespace delegation)
    # ---------------------------------------------------------

    def _candidate_urls(
        self,
        *,
        artifact_class: ArtifactClass,
        identifier: Tuple,
        role: Role,
    ) -> List[str]:
        """
        Delegate namespace logic to GitHubURLBuilder.

        Contract:
        - Returns [] if no namespace-valid URL exists for this role
        - Resolver MUST treat [] as a hard skip and rehash
        """
        urls = self.url_builder.urls_for(
            artifact_class.name,
            identifier,
            role,
        )

        return [u for u in urls if isinstance(u, str) and u.strip()]

    # ---------------------------------------------------------
    # Deterministic single-URL selection
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
        id_material = "|".join(str(x) for x in identifier)
        mix = f"{base_seed}|{epoch}|{artifact_class.name}|{role}|{id_material}"
        h = self._hash_to_int(mix)
        return allowed_urls[h % len(allowed_urls)]
