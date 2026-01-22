from __future__ import annotations

import hashlib
from typing import Tuple


def _stable_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def generate_placeholder_stegotext(
    *,
    epoch: int,
    artifact_class: str,
    role: str,
    url: str,
) -> tuple[str, str, str]:
    """
    Deterministically generate placeholder stegotext and its meaning + semantic_ref.

    Output is intentionally:
    - short
    - not cramped
    - no redundant fields
    """

    # Stable ref tied to what the adversary would observe (epoch/role/class/url)
    semantic_ref = f"sem_{_stable_hash(f'{epoch}|{role}|{artifact_class}|{url}')}"

    # Keep stegotext minimal, realistic-looking, and not "crufty"
    stegotext = (
        "Quick update:\n"
        "I’ll follow up with details after I finish validating the results.\n"
        "Thanks!"
    )

    # Meaning is for *your* debugging / scaffolding only (still deterministic)
    meaning = f"Covert sync marker for epoch {epoch}."

    return stegotext, meaning, semantic_ref
