"""
token_binning_placeholder.py

TEMPORARY placeholder steganographic encoder / decoder.

This module implements a *fake* token-binning system that:
- Preserves the correct interfaces
- Preserves the correct control flow
- Preserves the correct research semantics

IMPORTANT:
- This is NOT real steganography.
- This MUST be replaced with a real token-binning scheme later.
"""

from __future__ import annotations

import hashlib


# ============================================================
# Helpers
# ============================================================

def _stable_tag(*parts: str) -> str:
    """
    Deterministically derive a short tag from inputs.
    Used to simulate "token binning" structure.
    """
    h = hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()
    return h[:8]


# ============================================================
# Encoder (Sender side)
# ============================================================

def encode_secret_message(
    *,
    secret_message: str,
    epoch: int,
    artifact_class: str,
) -> str:
    """
    Encode a SECRET message into benign-looking text.

    This is a placeholder that simulates token binning by
    embedding a reversible tag.

    Parameters
    ----------
    secret_message : str
        The confidential message the sender wants to transmit.
    epoch : int
        Current epoch number.
    artifact_class : str
        Artifact used for routing (Issue, PR, Commit, etc.).

    Returns
    -------
    benign_text : str
        Text that appears benign and can be posted publicly.
    """

    tag = _stable_tag(secret_message, str(epoch), artifact_class)

    benign_text = (
        "Amazing issue — thanks for opening this! "
        "The discussion so far has been really helpful. "
        f"[ref:{tag}]"
    )

    return benign_text


# ============================================================
# Decoder (Receiver side)
# ============================================================

def decode_benign_message(
    *,
    benign_text: str,
    epoch: int,
    artifact_class: str,
) -> str:
    """
    Decode a benign-looking message back into the secret.

    Since this is a placeholder, we do NOT recover the original
    text. Instead, we simulate successful decoding.

    In the real system, this will:
    - Parse token bins
    - Reconstruct bitstream
    - Decode secret message

    Returns
    -------
    secret_message : str
        Simulated recovered secret message.
    """

    # Extract fake tag if present
    tag = "unknown"
    if "[ref:" in benign_text:
        try:
            tag = benign_text.split("[ref:")[1].split("]")[0]
        except Exception:
            pass

    decoded_message = (
        "[DECODED SECRET MESSAGE — PLACEHOLDER]\n"
        f"(epoch={epoch}, artifact={artifact_class}, tag={tag})\n\n"
        "This is where the original secret message would be recovered.\n"
        "Replace this placeholder with real token-binning decoding."
    )

    return decoded_message
