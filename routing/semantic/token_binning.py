from __future__ import annotations

import base64
import json
import os
from typing import Dict, Any, List, Tuple

import requests

# ============================================================
# OpenAI client
# ============================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY must be set")


def chat_completion(messages: List[Dict[str, str]], max_tokens: int) -> str:
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "messages": messages,
            "temperature": 0.4,  # conservative, evidence-biased
            "max_tokens": max_tokens,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


# ============================================================
# Configuration
# ============================================================

TOKENS_PER_SENTENCE_EST = 18
MAX_SENTENCES_PER_ARTIFACT = 4

# Explicit payload marker is for controlled testing only
EXPLICIT_PAYLOAD_FOR_TESTING = False

BITS_PER_SENTENCE = 2


# ============================================================
# Token binning vocabulary (VERY COMMON WORDS)
# ============================================================

TOKEN_BINS: Dict[str, List[str]] = {
    "slightly": ["slightly", "somewhat", "a bit", "a little"],
    "important": ["important", "significant", "notable", "meaningful"],
    "consider": ["consider", "review", "look at", "evaluate"],
    "change": ["change", "adjustment", "update", "modification"],
}


REVERSE_TOKEN_BINS: Dict[str, Tuple[str, int]] = {}
for base, options in TOKEN_BINS.items():
    for idx, word in enumerate(options):
        REVERSE_TOKEN_BINS[word] = (base, idx)


# ============================================================
# Surface classification
# ============================================================

def _is_comment(kind: str) -> bool:
    return isinstance(kind, str) and kind.endswith("Comment")


def surface_mode(artifact_class: str, kind: str) -> str:
    ac = (artifact_class or "").strip()
    k = (kind or "").strip()

    if _is_comment(k) or ac.endswith("Comment"):
        return "reply_comment"
    if ac in ("Issue", "PullRequest"):
        return "edit_body"
    return "observe_only"


# ============================================================
# Reply target resolution
# ============================================================

def resolve_reply_target(artifact: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    kind = artifact.get("kind", "")

    if _is_comment(kind):
        parent_kind = artifact.get("parent_kind")
        parent_text = artifact.get("parent_excerpt")
        if isinstance(parent_kind, str) and isinstance(parent_text, str) and parent_text.strip():
            return parent_kind, {
                "kind": parent_kind,
                "existing_text": parent_text.strip(),
            }

    return kind, artifact


# ============================================================
# Prompt rules (DIFF-AWARE)
# ============================================================

def common_rules(has_diff: bool) -> List[str]:
    rules = [
        "ASCII characters only",
        "Write like a real GitHub user",
        "No assistant or chatbot language",
        "No lists, headings, or markdown",
        "Each sentence must be complete and natural",
        "End with a complete sentence",
    ]

    if not has_diff:
        rules += [
            "Do not claim knowledge of code behavior or implementation details",
            "Avoid phrases like 'current implementation' or 'this code'",
            "Frame statements as exploratory or descriptive only",
        ]

    return rules


def rules_for(
    reply_kind: str,
    surface: str,
    is_edit: bool,
    has_diff: bool,
) -> List[str]:
    rules = common_rules(has_diff)

    if surface == "reply_comment":
        rules += [
            "Write as a direct reply to the discussion",
            "Respond to the substance of the context",
            "Do not summarize the repository or restate the artifact",
        ]

    if surface == "edit_body":
        rules += [
            "Write as an edit to the existing text, not a reply",
            "Preserve the intent and scope of the existing text",
            "Refine or clarify what is already written",
            "Do not replace the entire description with generic content",
        ]

    if reply_kind == "Issue":
        rules += ["Stay aligned with the reported problem or clarification"]

    if reply_kind == "PullRequest":
        rules += [
            "Describe or refine what the change does",
            "Mention testing only if supported by diffs or existing text",
        ]

    return rules


# ============================================================
# Text generation (UNCHANGED)
# ============================================================

def realize_stegotext(
    *,
    artifact_class: str,
    artifact: Dict[str, Any],
) -> str:
    kind = artifact.get("kind", "")
    surface = surface_mode(artifact_class, kind)

    if surface == "observe_only":
        return ""

    reply_kind, reply_target = resolve_reply_target(artifact)

    existing_text = (
        reply_target.get("existing_text")
        or artifact.get("body_excerpt")
        or artifact.get("text")
        or ""
    )

    diff_files = artifact.get("diff_files", []) or []
    has_diff = bool(diff_files)

    is_edit = surface == "edit_body" and bool(existing_text.strip())

    rules = rules_for(reply_kind, surface, is_edit, has_diff)

    context: Dict[str, Any] = {
        "artifact_kind": reply_kind,
        "existing_text": existing_text.strip(),
    }

    if has_diff:
        context["diff_files"] = [
            {
                "filename": f.get("filename"),
                "status": f.get("status"),
                "patch_excerpt": f.get("patch_excerpt", ""),
            }
            for f in diff_files
        ]

    instruction = (
        f"Write exactly {MAX_SENTENCES_PER_ARTIFACT} sentences "
        + ("that revise and refine the existing text below." if is_edit else "appropriate for this GitHub surface.")
    )

    prompt = (
        instruction
        + "\n\nRules:\n"
        + "\n".join(f"- {r}" for r in rules)
        + "\n\nContext:\n"
        + json.dumps(context, indent=2)
    )

    text = chat_completion(
        messages=[
            {"role": "system", "content": "Output only the requested sentences as plain text."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=MAX_SENTENCES_PER_ARTIFACT * TOKENS_PER_SENTENCE_EST,
    )

    text = text.encode("ascii", errors="ignore").decode("ascii").strip()
    if text and text[-1] not in ".!?":
        text += "."

    return text


# ============================================================
# Token binning helpers
# ============================================================

def _bytes_to_bits(data: bytes) -> List[int]:
    bits: List[int] = []
    for b in data:
        for i in range(7, -1, -1):
            bits.append((b >> i) & 1)
    return bits


def _bits_to_bytes(bits: List[int]) -> bytes:
    out = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for b in bits[i:i + 8]:
            byte = (byte << 1) | b
        out.append(byte)
    return bytes(out)


def _take_bits(bits: List[int], n: int) -> int:
    val = 0
    for _ in range(n):
        val = (val << 1) | (bits.pop(0) if bits else 0)
    return val


def _embed_bits(sentence: str, bin_value: int) -> str:
    for base, options in TOKEN_BINS.items():
        if base in sentence:
            return sentence.replace(base, options[bin_value % 4], 1)
    return sentence


def _extract_bits(sentence: str) -> List[int]:
    bits: List[int] = []
    for word in sentence.split():
        clean = word.strip(".,!?")
        if clean in REVERSE_TOKEN_BINS:
            _, idx = REVERSE_TOKEN_BINS[clean]
            bits.append((idx >> 1) & 1)
            bits.append(idx & 1)
    return bits


# ============================================================
# Public API (augmented, not replaced)
# ============================================================

def encode_secret_message(
    *,
    secret_message: str,
    epoch: int,
    artifact_class: str,
    artifact_context: Dict[str, Any],
) -> str:
    benign = realize_stegotext(
        artifact_class=artifact_class,
        artifact=artifact_context,
    )

    if not benign or not secret_message:
        return benign

    bits = _bytes_to_bits(secret_message.encode("utf-8"))
    sentences = [s.strip() for s in benign.split(".") if s.strip()]

    out: List[str] = []
    for s in sentences:
        if bits:
            b = _take_bits(bits, BITS_PER_SENTENCE)
            s = _embed_bits(s, b)
        out.append(s + ".")

    return " ".join(out)


def decode_benign_message(
    *,
    benign_text: str,
    epoch: int,
    artifact_class: str,
    artifact_context: Dict[str, Any],
) -> str:
    bits: List[int] = []

    for sentence in benign_text.split("."):
        bits.extend(_extract_bits(sentence))

    if not bits:
        return ""

    try:
        raw = _bits_to_bytes(bits)
        return raw.decode("utf-8", errors="ignore").rstrip("\x00")
    except Exception:
        return ""

