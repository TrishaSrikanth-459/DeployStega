"""
experiment_context.py

Immutable experiment configuration loader.

Responsibilities:
- Load experiment-scoped configuration from a manifest
- Provide sender / receiver IDs
- Provide epoch definition parameters
- Validate all experiment-wide invariants at startup
- Provide snapshot path

Non-responsibilities:
- No routing logic
- No resolver logic
- No epoch advancement
- No network access
"""

from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Final


# ============================================================
# Constants
# ============================================================

# 128-bit lowercase hex ID (32 hex chars)
HEX_128_RE: Final = re.compile(r"^[0-9a-f]{32}$")


# ============================================================
# Experiment Context
# ============================================================

class ExperimentContext:
    """
    Immutable experiment configuration shared by sender and receiver.

    All fields are fixed at experiment start and MUST be shared
    out-of-band prior to any routing or steganographic activity.
    """

    # ---------------------------------------------------------
    # Construction
    # ---------------------------------------------------------

    def __init__(self, manifest_path: str):
        path = Path(manifest_path)

        if not path.exists():
            raise FileNotFoundError(f"Experiment manifest not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # ------------------------
        # Required fields
        # ------------------------

        try:
            self.experiment_id: str = data["experiment_id"]
            self.snapshot_path: str = data["snapshot"]

            participants = data["participants"]
            self.sender_id: str = participants["sender"]["id"]
            self.receiver_id: str = participants["receiver"]["id"]

            epoch_cfg = data["epoch"]
            self.epoch_duration_seconds: int = epoch_cfg["duration_seconds"]
            self.epoch_origin_unix: int = epoch_cfg["origin_unix"]
            self.epoch_window_size: int = epoch_cfg["window_size"]

        except KeyError as e:
            raise ValueError(
                f"Malformed experiment manifest; missing field: {e}"
            ) from e

        # ------------------------
        # Validation (startup only)
        # ------------------------

        self._validate_experiment_id()
        self._validate_ids()
        self._validate_snapshot_path()
        self._validate_epoch_definition()

    # =========================================================
    # Validation helpers
    # =========================================================

    def _validate_experiment_id(self) -> None:
        if not isinstance(self.experiment_id, str) or not self.experiment_id:
            raise ValueError("experiment_id must be a non-empty string")

    def _validate_ids(self) -> None:
        """
        Enforce strict, experiment-start ID correctness.

        IDs are opaque session identifiers. They encode:
        - no role information
        - no timing information
        - no semantic meaning
        """

        for label, sid in [
            ("sender_id", self.sender_id),
            ("receiver_id", self.receiver_id),
        ]:
            if not isinstance(sid, str):
                raise ValueError(f"{label} must be a string")

            if not HEX_128_RE.fullmatch(sid):
                raise ValueError(
                    f"{label} malformed: expected 128-bit lowercase hex ID"
                )

    def _validate_snapshot_path(self) -> None:
        path = Path(self.snapshot_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Snapshot file does not exist: {path}"
            )

    def _validate_epoch_definition(self) -> None:
        """
        Validate epoch definition parameters.

        Epochs are logical indices derived from a shared definition,
        NOT synchronized clocks or live coordination.
        """

        if not isinstance(self.epoch_duration_seconds, int) or self.epoch_duration_seconds <= 0:
            raise ValueError("epoch.duration_seconds must be a positive integer")

        if not isinstance(self.epoch_origin_unix, int) or self.epoch_origin_unix <= 0:
            raise ValueError("epoch.origin_unix must be a positive UNIX timestamp")

        if not isinstance(self.epoch_window_size, int) or self.epoch_window_size <= 0:
            raise ValueError("epoch.window_size must be a positive integer")

    # =========================================================
    # Identity verification (runtime check)
    # =========================================================

    def verify_identity(self, role: str, provided_id: str) -> bool:
        """
        Verify that the provided ID matches the experiment-bound ID
        for the declared role.

        Enforces:
        - sender cannot masquerade as receiver
        - receiver cannot masquerade as sender
        - identity is fixed at experiment start
        """

        if role == "sender":
            return provided_id == self.sender_id

        if role == "receiver":
            return provided_id == self.receiver_id

        raise ValueError(f"Unknown role: {role}")


# ============================================================
# Loader convenience
# ============================================================

def load_experiment_context(
    manifest_path: str = "experiments/experiment_manifest.json",
) -> ExperimentContext:
    """
    Load and validate the experiment context.

    This is the ONLY entrypoint interactive scripts should use.
    """
    return ExperimentContext(manifest_path)
