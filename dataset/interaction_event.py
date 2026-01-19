"""
dataset/interaction_event.py

Defines the atomic unit observed by the adversary.

An InteractionEvent represents a *single log-visible interaction* enriched
with optional semantic payloads when explicitly enabled by the experiment.

Design principles:
- Faithful to application logs
- Deterministic
- Feature-extractor friendly
- Semantic content is OPTIONAL but FIRST-CLASS
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple


@dataclass(frozen=True)
class InteractionEvent:
    """
    One adversary-visible interaction event.

    Required:
      - timestamp: float (unix seconds)
      - action_type: str
      - artifact_ids: tuple[Any, ...]

    Optional:
      - metadata: tuple[(key, value), ...]
      - semantic_ref: opaque identifier linking to semantic artifact
      - semantic_content: raw semantic text (if included)
      - semantic_label: "benign" | "covert"
      - semantic_type: descriptive tag (e.g., issue_body, pr_comment)
    """

    timestamp: float
    action_type: str
    artifact_ids: Tuple[Any, ...]

    metadata: Tuple[Tuple[Any, Any], ...] = ()

    # -------------------------------
    # Semantic payload (optional)
    # -------------------------------
    semantic_ref: Optional[str] = None
    semantic_content: Optional[str] = None
    semantic_label: Optional[str] = None
    semantic_type: Optional[str] = None

    # -------------------------------
    # Convenience helpers
    # -------------------------------

    def has_semantic(self) -> bool:
        return self.semantic_ref is not None

    def semantic_tuple(self) -> Optional[Tuple[str, str, str, str]]:
        """
        Returns a stable semantic tuple if semantic content exists.
        """
        if not self.has_semantic():
            return None
        return (
            self.semantic_ref,
            self.semantic_type or "",
            self.semantic_label or "",
            self.semantic_content or "",
        )
