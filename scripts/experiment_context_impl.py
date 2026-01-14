from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Final, Optional

# 128-bit lowercase hex ID (32 hex chars)
HEX_128_RE: Final = re.compile(r"^[0-9a-f]{32}$")


class ExperimentContext:
    """
    Immutable experiment configuration loader.

    The experiment manifest is the single source of truth for:
    - experiment identity
    - participant identifiers
    - epoch definition
    - snapshot location

    The snapshot is a routing artifact freeze and does NOT carry
    experiment identity.
    """

    def __init__(self, manifest_path: str):
        path = Path(manifest_path)
        if not path.exists():
            raise FileNotFoundError(f"Experiment manifest not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.experiment_id = data["experiment_id"]
        self.snapshot_path = data["snapshot"]

        participants = data["participants"]
        self.sender_id = participants["sender"]["id"]
        self.receiver_id = participants["receiver"]["id"]

        epoch = data["epoch"]
        self.epoch_origin_unix = epoch["origin_unix"]
        self.epoch_duration_seconds = epoch["duration_seconds"]
        self.epoch_window_size = epoch["window_size"]
        self.epoch_end_unix: Optional[int] = epoch.get("end_unix")

        self._validate_ids()
        self._validate_snapshot()
        self._validate_epoch()

    # ============================================================
    # Validation helpers
    # ============================================================

    def _validate_ids(self) -> None:
        for label, sid in [("sender_id", self.sender_id), ("receiver_id", self.receiver_id)]:
            if not isinstance(sid, str) or not HEX_128_RE.fullmatch(sid):
                raise ValueError(f"{label} malformed: expected 128-bit lowercase hex ID")

    def _validate_snapshot(self) -> None:
        """
        Validate that the snapshot exists and is structurally usable.

        The snapshot is required to be built BEFORE the experiment
        epoch origin time, but does not encode experiment identity.
        """
        path = Path(self.snapshot_path)
        if not path.exists():
            raise RuntimeError(
                "Snapshot missing.\n"
                "You must run build_snapshot.py before starting the experiment."
            )

        with open(path, "r", encoding="utf-8") as f:
            snap = json.load(f)

        built_at = snap.get("built_at_unix")
        if not isinstance(built_at, int):
            raise RuntimeError("Snapshot missing or invalid 'built_at_unix' timestamp")

        if built_at >= self.epoch_origin_unix:
            raise RuntimeError(
                "Snapshot was built after epoch origin time.\n"
                "Snapshot must be built before the experiment starts."
            )

        artifacts = snap.get("artifacts")
        if not isinstance(artifacts, dict) or not artifacts:
            raise RuntimeError("Snapshot contains no routing artifacts")

    def _validate_epoch(self) -> None:
        if not isinstance(self.epoch_duration_seconds, int) or self.epoch_duration_seconds <= 0:
            raise ValueError("epoch.duration_seconds must be positive")

        if not isinstance(self.epoch_origin_unix, int) or self.epoch_origin_unix <= 0:
            raise ValueError("epoch.origin_unix invalid")

        if not isinstance(self.epoch_window_size, int) or self.epoch_window_size <= 0:
            raise ValueError("epoch.window_size must be positive")

        if self.epoch_end_unix is not None:
            if not isinstance(self.epoch_end_unix, int) or self.epoch_end_unix <= 0:
                raise ValueError("epoch.end_unix invalid")
            if self.epoch_end_unix <= self.epoch_origin_unix:
                raise ValueError("epoch.end_unix must be after epoch.origin_unix")

    # ============================================================
    # Identity verification
    # ============================================================

    def verify_identity(self, role: str, provided_id: str) -> bool:
        if role == "sender":
            return provided_id == self.sender_id
        if role == "receiver":
            return provided_id == self.receiver_id
        raise ValueError("Unknown role")
