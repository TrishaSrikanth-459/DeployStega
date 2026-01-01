"""
bootstrap_experiment.py

Out-of-band experiment bootstrap utility.

This script:
- Generates opaque sender and receiver identifiers
- Persists them into the experiment manifest
- Performs NO routing, encoding, decoding, timing, or GitHub access

IMPORTANT:
- These identifiers are NOT cryptographic keys.
- They are used ONLY as deterministic PRNG inputs for the dead-drop resolver:
      digest = H(epoch || senderID || receiverID)
- Overwriting existing IDs will break sender/receiver synchronization.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

MANIFEST_PATH = Path("experiments/experiment_manifest.json")


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def generate_id() -> str:
    """
    Generate a 128-bit opaque session identifier.

    Properties:
    - Uniformly random
    - Non-semantic
    - Unlinkable to GitHub identity
    - Used ONLY for deterministic routing synchronization
    """
    return secrets.token_hex(16)


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

def main() -> None:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Experiment manifest not found: {MANIFEST_PATH}")

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    participants = manifest.get("participants")
    if not isinstance(participants, dict):
        raise RuntimeError("Malformed manifest: missing 'participants' section")

    sender = participants.get("sender", {})
    receiver = participants.get("receiver", {})

    # ---------------------------------------------------------------
    # HARD SAFETY CHECK — prevent silent desynchronization
    # ---------------------------------------------------------------

    if sender.get("id") or receiver.get("id"):
        raise RuntimeError(
            "Participant IDs already exist in the manifest.\n"
            "Refusing to overwrite to prevent sender/receiver desynchronization.\n"
            "Delete the IDs explicitly if you intend to re-bootstrap."
        )

    # ---------------------------------------------------------------
    # Generate opaque identifiers
    # ---------------------------------------------------------------

    sender_id = generate_id()
    receiver_id = generate_id()

    sender["id"] = sender_id
    receiver["id"] = receiver_id

    participants["sender"] = sender
    participants["receiver"] = receiver
    manifest["participants"] = participants

    # ---------------------------------------------------------------
    # Persist manifest
    # ---------------------------------------------------------------

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("✅ Experiment participants bootstrapped (out-of-band)")
    print("Sender ID  :", sender_id)
    print("Receiver ID:", receiver_id)
    print("\n⚠️  These IDs must be shared privately and remain fixed for the experiment.")


# -------------------------------------------------------------------
# Entrypoint
# -------------------------------------------------------------------

if __name__ == "__main__":
    main()
