from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ============================================================
# Guardrail decision object
# ============================================================

@dataclass(frozen=True)
class GuardrailResult:
    """
    Result of semantic validation.

    accepted:
        True if the message may proceed to encoding.

    edited_text:
        Suggested edited version (if fixable), else None.

    reason:
        Human-readable explanation for rejection or edit.
    """
    accepted: bool
    edited_text: Optional[str]
    reason: Optional[str]


# ============================================================
# Semantic guardrails (PLACEHOLDER)
# ============================================================

class SemanticGuardrails:
    """
    Enforces semantic constraints BEFORE token binning.

    This is a TEMPORARY placeholder implementation.

    Later versions will incorporate:
      - PPL thresholds
      - KL divergence
      - token entropy budgets
      - artifact-specific semantic capacity
      - sender behavioral history

    Current guarantees:
      - No silent modification
      - Deterministic behavior
      - Fully auditable decisions
    """

    MAX_CHARS = 500

    def validate(
        self,
        *,
        text: str,
        artifact_class: str,
        epoch: int,
    ) -> GuardrailResult:
        """
        Validate or suggest edits to sender-provided semantic content.

        Returns a GuardrailResult that the caller MUST respect.
        """

        cleaned = text.strip()

        # --------------------------------------------
        # Rule 1: Non-empty semantic content
        # --------------------------------------------
        if not cleaned:
            return GuardrailResult(
                accepted=False,
                edited_text=None,
                reason="Message is empty after stripping whitespace.",
            )

        # --------------------------------------------
        # Rule 2: Length cap (artifact-agnostic for now)
        # --------------------------------------------
        if len(cleaned) > self.MAX_CHARS:
            truncated = cleaned[: self.MAX_CHARS]

            return GuardrailResult(
                accepted=False,
                edited_text=truncated,
                reason=(
                    f"Message exceeds maximum length "
                    f"({len(cleaned)} > {self.MAX_CHARS}). "
                    f"Suggested truncation."
                ),
            )

        # --------------------------------------------
        # Rule 3: Placeholder semantic budget hook
        # --------------------------------------------
        # NOTE:
        # This is where KL / PPL / bin-capacity logic
        # will be inserted later.
        #
        # Example (future):
        #   if kl_score > artifact_budget:
        #       reject
        #
        # For now, everything else is allowed.

        return GuardrailResult(
            accepted=True,
            edited_text=None,
            reason=None,
        )
