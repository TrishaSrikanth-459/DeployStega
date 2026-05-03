from __future__ import annotations

import json
import os
import re
import math
import random
from typing import Dict, Any, List, Tuple, Optional, Set
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
from urllib.parse import urlparse, urlunparse

from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam
from openai import AzureOpenAI

# ============================================================
# Configuration
# ============================================================

AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT_RAW = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
AZURE_OPENAI_DEPLOYMENT = (
    os.getenv("AZURE_OPENAI_DEPLOYMENT")
    or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
)


def _normalize_azure_endpoint(endpoint: Optional[str]) -> Optional[str]:
    if not endpoint:
        return endpoint

    parsed = urlparse(endpoint)
    if not parsed.scheme or not parsed.netloc:
        return endpoint.rstrip("/")

    normalized = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    return normalized.rstrip("/")


AZURE_OPENAI_ENDPOINT = _normalize_azure_endpoint(AZURE_OPENAI_ENDPOINT_RAW)

if not AZURE_OPENAI_API_KEY:
    raise RuntimeError("AZURE_OPENAI_API_KEY must be set")
if not AZURE_OPENAI_ENDPOINT:
    raise RuntimeError("AZURE_OPENAI_ENDPOINT must be set")
if not AZURE_OPENAI_DEPLOYMENT:
    raise RuntimeError("AZURE_OPENAI_DEPLOYMENT or AZURE_OPENAI_DEPLOYMENT_NAME must be set")

client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version=AZURE_OPENAI_API_VERSION,
)


# ============================================================
# Diversification config
# ============================================================
# These constants drive prompt-layer diversification so covert chunks do not
# all collapse onto a single "polished GitHub note" attractor in embedding /
# perplexity space. They never affect the bit-encoding contract.

# Personas rotated per chunk. Each entry is (label, system_prompt_addendum).
PERSONAS: List[Tuple[str, str]] = [
    (
        "triager",
        "Write like a maintainer triaging issues. Be concise, sometimes refer to "
        "labels, duplicates, or repro steps. Short factual sentences are normal.",
    ),
    (
        "reviewer",
        "Write like a code reviewer leaving a small inline note. Reference "
        "behavior, edge cases, or naming. Keep it brief and direct.",
    ),
    (
        "contributor",
        "Write like a contributor explaining a small change. Mention motivation "
        "and impact in plain language. Keep it short and human.",
    ),
    (
        "maintainer",
        "Write like a project maintainer leaving a brief follow-up. Tone may be "
        "informal: 'thanks', 'good catch', short acknowledgments are fine.",
    ),
    (
        "ops",
        "Write like an engineer reporting a small operational result: a build, "
        "test, deploy, or rollout note. Plain and matter-of-fact.",
    ),
    (
        "docs",
        "Write like a contributor noting a docs or comment cleanup. Brief, "
        "specific, and slightly informal.",
    ),
]

# Surface-form variants sampled per chunk. Each defines a set of permissions
# that the prompt then reflects. Approximate weights mirror what real GitHub
# Issue/PR edit text looks like.
SURFACE_FORMS: List[Dict[str, Any]] = [
    {  # short prose, terminal period
        "label": "short_prose",
        "weight": 30,
        "sentence_min": 2, "sentence_max": 3,
        "allow_bullets": False, "allow_code_block": False,
        "force_terminal_period": True,
    },
    {  # medium prose
        "label": "medium_prose",
        "weight": 25,
        "sentence_min": 3, "sentence_max": 5,
        "allow_bullets": False, "allow_code_block": False,
        "force_terminal_period": True,
    },
    {  # bullet list
        "label": "bullets",
        "weight": 15,
        "sentence_min": 3, "sentence_max": 6,
        "allow_bullets": True, "allow_code_block": False,
        "force_terminal_period": False,
    },
    {  # inline-code-heavy prose (no fences)
        "label": "inline_code_prose",
        "weight": 10,
        "sentence_min": 2, "sentence_max": 4,
        "allow_bullets": False, "allow_code_block": False,
        "force_terminal_period": True,
    },
    {  # terse one-liner
        "label": "terse",
        "weight": 8,
        "sentence_min": 1, "sentence_max": 2,
        "allow_bullets": False, "allow_code_block": False,
        "force_terminal_period": False,
    },
    {  # prose plus a small fenced code block
        "label": "code_block",
        "weight": 7,
        "sentence_min": 2, "sentence_max": 4,
        "allow_bullets": False, "allow_code_block": True,
        "force_terminal_period": True,
    },
    {  # casual no-period
        "label": "casual_no_period",
        "weight": 5,
        "sentence_min": 1, "sentence_max": 3,
        "allow_bullets": False, "allow_code_block": False,
        "force_terminal_period": False,
    },
]

# Sampling parameter band per chunk. Higher temperature / lower top_p
# produces more varied (and therefore higher-perplexity) prose, which moves
# the GPT-2 perplexity profile closer to real GitHub text.
SAMPLING_BAND: Dict[str, Tuple[float, float]] = {
    "temperature": (0.7, 1.05),
    "top_p": (0.85, 0.97),
}

# Default per-chunk capacity. Lower than the legacy 96/128 so each chunk
# carries ~8 forced tokens spread across several sentences instead of ~24
# stacked into 3-6.
DEFAULT_TARGET_BITS_PER_CHUNK = 32
DEFAULT_MAX_CHOICES_PER_CHUNK = 8

# Search paths for the optional benign exemplar corpus. The encoder degrades
# gracefully (no few-shot, no benign-style validator) when this is missing.
DEFAULT_BENIGN_EXEMPLARS_FILENAME = "benign_traces.jsonl"
BENIGN_EXEMPLARS_ENV_VAR = "STEGO_BENIGN_EXEMPLARS_PATH"


# ============================================================
# BYTE-LEVEL Semantic Encoder
# ============================================================

class ByteLevelSemanticEncoder:
    ARTIFACT_TYPE_MAP = {
        "Issue": "GitHub issue",
        "PullRequest": "pull request",
        "GitTag": "release tag",
        "Label": "label",
        "Milestone": "milestone",
        "IssueComment": "issue comment",
        "PullRequestComment": "pull request comment",
        "PullRequestReviewComment": "pull request review comment",
        "CommitComment": "commit comment",
        "Repository": "repository",
        "Commit": "commit",
    }

    COMMENT_CLASSES = {
        "IssueComment",
        "PullRequestComment",
        "PullRequestReviewComment",
        "CommitComment",
    }

    ARTIFACT_CYCLE = [
        ("IssueComment", True),
        ("PullRequestComment", True),
        ("CommitComment", True),
        ("Issue", False),
        ("PullRequest", False),
        ("GitTag", False),
    ]

    TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*")

    def __init__(
        self,
        bins_path: str = None,
        quiet: bool = False,
        benign_exemplars_path: Optional[str] = None,
        target_bits_per_chunk: int = DEFAULT_TARGET_BITS_PER_CHUNK,
        max_choices_per_chunk: int = DEFAULT_MAX_CHOICES_PER_CHUNK,
        enable_surface_validator: bool = False,
    ):
        self.quiet = quiet
        self.bins = []
        self.large_bins = []
        self.medium_bins = []
        self.small_bins = []
        self.tiny_bins = []

        # Diversification knobs
        self.target_bits_per_chunk = target_bits_per_chunk
        self.max_choices_per_chunk = max_choices_per_chunk
        # The legacy LLM "naturalness" validator pulls every accepted output
        # toward one polished-prose attractor, which is part of the semantic
        # detectability problem. Default off; set True to restore the old gate.
        self.enable_surface_validator = enable_surface_validator

        base_dir = os.path.dirname(os.path.abspath(__file__))
        fixed_bins_path = os.path.join(base_dir, "../../token_binning_data/bins_k16.json")
        self._load_byte_bins(fixed_bins_path)

        # Optional benign exemplar corpus, grouped by artifact_class. Used for
        # in-context style demonstrations in the prompt. Resolution order:
        # explicit arg > env var > common candidate paths > none.
        self._exemplars_by_class: Dict[str, List[str]] = self._load_benign_exemplars(
            benign_exemplars_path
        )

        if not self.quiet:
            print("\nBYTE-LEVEL ENCODING CAPACITY")
            print(f"  Large bins (256+ words): {len(self.large_bins)}")
            print(f"  Medium bins (64-255 words): {len(self.medium_bins)}")
            print(f"  Small bins (16-63 words): {len(self.small_bins)}")
            print(f"  Tiny bins (2-15 words): {len(self.tiny_bins)}")
            print(f"  target_bits_per_chunk={self.target_bits_per_chunk}")
            print(f"  max_choices_per_chunk={self.max_choices_per_chunk}")
            exemplar_classes = sorted(self._exemplars_by_class)
            print(f"  benign exemplars loaded for: {exemplar_classes or '(none)'}")

        if len(self.large_bins) == 0 and len(self.medium_bins) == 0 and len(self.small_bins) < 2:
            raise RuntimeError(
                "No usable bins to encode. Need at least 2 bins with size>=16 "
                "(small/medium/large) to encode bytes as two nibbles."
            )

    def _load_byte_bins(self, bins_path: str):
        if not self.quiet:
            print(f"Loading byte-level bins from {bins_path}...")

        with open(bins_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        bins_data = data["bins"] if "bins" in data else data

        for bin_id, tokens in enumerate(bins_data):
            if len(tokens) < 2:
                continue

            clean_tokens = [str(tok).strip() for tok in tokens if str(tok).strip()]
            size = len(clean_tokens)

            bin_info = {
                "bin_id": bin_id,
                "tokens": clean_tokens,
                "size": size,
                "capacity_bits": int(math.log2(size)) if size >= 2 else 1,
            }

            self.bins.append(bin_info)

            if size >= 256:
                self.large_bins.append(bin_info)
            elif size >= 64:
                self.medium_bins.append(bin_info)
            elif size >= 16:
                self.small_bins.append(bin_info)
            else:
                self.tiny_bins.append(bin_info)

        if not self.quiet:
            print(f"Loaded {len(self.bins)} byte-level bins")

    # ------------------------------------------------------------
    # Diversification helpers (no effect on bit-encoding contract)
    # ------------------------------------------------------------

    def _candidate_exemplar_paths(self, explicit: Optional[str]) -> List[str]:
        candidates: List[str] = []
        if explicit:
            candidates.append(explicit)
        env_path = os.environ.get(BENIGN_EXEMPLARS_ENV_VAR)
        if env_path:
            candidates.append(env_path)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        for rel in (
            f"../../{DEFAULT_BENIGN_EXEMPLARS_FILENAME}",
            f"../../../{DEFAULT_BENIGN_EXEMPLARS_FILENAME}",
            f"../../data/{DEFAULT_BENIGN_EXEMPLARS_FILENAME}",
            f"../../experiments/{DEFAULT_BENIGN_EXEMPLARS_FILENAME}",
        ):
            candidates.append(os.path.normpath(os.path.join(base_dir, rel)))
        # Deduplicate while preserving order
        seen: Set[str] = set()
        ordered: List[str] = []
        for p in candidates:
            if p and p not in seen:
                seen.add(p)
                ordered.append(p)
        return ordered

    def _load_benign_exemplars(self, explicit: Optional[str]) -> Dict[str, List[str]]:
        """Load benign texts grouped by artifact_class.

        Source schema: JSONL with at least 'artifact_class' and 'semantic_text'.
        Missing file is not an error; few-shot conditioning is then disabled.
        """
        for path in self._candidate_exemplar_paths(explicit):
            if not os.path.isfile(path):
                continue
            try:
                grouped: Dict[str, List[str]] = defaultdict(list)
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        cls = obj.get("artifact_class")
                        text = obj.get("semantic_text")
                        if not cls or not isinstance(text, str):
                            continue
                        text = text.strip()
                        if not text or len(text) > 1500:
                            continue
                        grouped[str(cls)].append(text)
                if grouped:
                    if not self.quiet:
                        print(f"Loaded benign exemplars from {path}")
                    return dict(grouped)
            except (OSError, UnicodeDecodeError):
                continue
        return {}

    @staticmethod
    def _chunk_seed(message_seed: int, chunk_idx: int) -> int:
        # Mix message-level seed with chunk index for per-chunk reproducibility
        return (message_seed ^ ((chunk_idx + 1) * 0x9E3779B97F4A7C15)) & 0xFFFFFFFF

    @staticmethod
    def _pick_persona(rng: random.Random) -> Tuple[str, str]:
        return rng.choice(PERSONAS)

    @staticmethod
    def _pick_surface_form(rng: random.Random, force_code_block: bool = False) -> Dict[str, Any]:
        if force_code_block:
            for sf in SURFACE_FORMS:
                if sf["label"] == "code_block":
                    return sf
        weights = [sf["weight"] for sf in SURFACE_FORMS]
        return rng.choices(SURFACE_FORMS, weights=weights, k=1)[0]

    def _pick_exemplars(
        self,
        rng: random.Random,
        artifact_class: str,
        k: int = 2,
    ) -> List[str]:
        if not self._exemplars_by_class:
            return []
        pool = self._exemplars_by_class.get(artifact_class)
        if not pool:
            # Fall back to any class so the model still sees real GitHub style
            pool = []
            for v in self._exemplars_by_class.values():
                pool.extend(v)
        if not pool:
            return []
        n = min(k, len(pool))
        return rng.sample(pool, n)

    def _sample_temperature(self, rng: random.Random) -> Tuple[float, float]:
        lo_t, hi_t = SAMPLING_BAND["temperature"]
        lo_p, hi_p = SAMPLING_BAND["top_p"]
        return rng.uniform(lo_t, hi_t), rng.uniform(lo_p, hi_p)

    def encode_message(self, message: str, context: Dict[str, Any]) -> tuple[list[Any], list[Any]]:
        if not self.quiet:
            print(f"\nBYTE-LEVEL ENCODING: {message!r}")

        message_bytes = message.encode("utf-8")
        if not self.quiet:
            print(f"  Message bytes: {len(message_bytes)}")
            print(f"  Message bits: {len(message_bytes) * 8}")

        choices = self._create_byte_choices(message_bytes)
        if not choices:
            raise RuntimeError(
                "Created 0 encoding choices. Need at least 2 bins with size>=16 "
                "or 1 bin with size>=256."
            )

        target_bits_per_chunk, max_choices_per_chunk = self._choose_chunking_params(choices)
        if not self.quiet:
            print(f"  Chunk target bits: {target_bits_per_chunk}")
            print(f"  Max choices per chunk: {max_choices_per_chunk}")

        chunks = self._byte_chunking(
            choices,
            target_bits_per_chunk=target_bits_per_chunk,
            max_choices_per_chunk=max_choices_per_chunk,
        )

        stegotexts: List[str] = []
        positions_data: List[Dict[str, Any]] = []
        used_words_global: Set[str] = set()
        previous_stegotexts: List[str] = []

        # Per-message seed lets persona / surface-form / sampling choices stay
        # reproducible across reruns of the same message while still varying
        # across messages and across chunks within a message.
        message_seed = int.from_bytes(
            hashlib.sha256(message_bytes).digest()[:8], "big"
        )

        # Forward the entire context dict (after defaulting required fields)
        # so the prompt builder can use any optional artifact-context keys the
        # caller supplied (parent_text, repo_language, file_paths, etc.).
        chunk_context = dict(context or {})
        chunk_context.setdefault("artifact_class", "IssueComment")
        chunk_context.setdefault("action", "view")

        for chunk_idx, chunk_choices in enumerate(chunks):
            if not self.quiet:
                print(f"\n  --- Chunk {chunk_idx + 1} ---")
                print(f"  Encoding {len(chunk_choices)} choices")

            chunk_text, chunk_positions = self._generate_byte_chunk(
                context=chunk_context,
                chunk_idx=chunk_idx,
                choices=chunk_choices,
                used_words_global=used_words_global,
                previous_stegotexts=previous_stegotexts,
                message_seed=message_seed,
            )

            stegotexts.append(chunk_text)
            previous_stegotexts.append(chunk_text)

            chunk_bits = sum(c.get("bits", 0) for c in chunk_choices)
            positions_data.append(
                {
                    "chunk_id": chunk_idx,
                    "choices": len(chunk_choices),
                    "encoded_bits": chunk_bits,
                    "positions": chunk_positions,
                    "text_preview": chunk_text[:160] + "..." if len(chunk_text) > 160 else chunk_text,
                }
            )

            for pos in chunk_positions:
                word = pos.get("chosen_word")
                if word:
                    used_words_global.add(word.lower())

        return stegotexts, positions_data

    def _create_byte_choices(self, message_bytes: bytes) -> List[Dict]:
        choices: List[Dict] = []

        for i, byte_value in enumerate(message_bytes):
            byte_choice = self._encode_byte(byte_value, i)
            if byte_choice is None:
                raise RuntimeError(
                    f"Byte {i} (0x{byte_value:02x}) could not be encoded with available bins."
                )

            if isinstance(byte_choice, list):
                choices.extend(byte_choice)
            else:
                choices.append(byte_choice)

        for idx, ch in enumerate(choices):
            ch["choice_id"] = idx

        return choices

    def _encode_byte(self, byte_value: int, byte_index: int) -> Optional[Dict | List[Dict]]:
        if self.large_bins:
            cluster = self.large_bins[byte_index % len(self.large_bins)]
            return {
                "byte_value": byte_value,
                "cluster_id": cluster["bin_id"],
                "cluster_words": cluster["tokens"],
                "target_index": byte_value % len(cluster["tokens"]),
                "bits": 8,
                "encoding_type": "byte",
                "byte_index": byte_index,
            }

        if len(self.medium_bins) >= 2:
            high_nibble = (byte_value >> 4) & 0x0F
            low_nibble = byte_value & 0x0F
            high_bin = self.medium_bins[byte_index % len(self.medium_bins)]
            low_bin = self.medium_bins[(byte_index + 1) % len(self.medium_bins)]

            if len(high_bin["tokens"]) >= 16 and len(low_bin["tokens"]) >= 16:
                return [
                    {
                        "nibble_value": high_nibble,
                        "cluster_id": high_bin["bin_id"],
                        "cluster_words": high_bin["tokens"],
                        "target_index": high_nibble,
                        "bits": 4,
                        "encoding_type": "high_nibble",
                        "byte_index": byte_index,
                    },
                    {
                        "nibble_value": low_nibble,
                        "cluster_id": low_bin["bin_id"],
                        "cluster_words": low_bin["tokens"],
                        "target_index": low_nibble,
                        "bits": 4,
                        "encoding_type": "low_nibble",
                        "byte_index": byte_index,
                    },
                ]

        if len(self.small_bins) >= 2:
            high_nibble = (byte_value >> 4) & 0x0F
            low_nibble = byte_value & 0x0F
            high_bin = self.small_bins[byte_index % len(self.small_bins)]
            low_bin = self.small_bins[(byte_index + 1) % len(self.small_bins)]

            if len(high_bin["tokens"]) >= 16 and len(low_bin["tokens"]) >= 16:
                return [
                    {
                        "nibble_value": high_nibble,
                        "cluster_id": high_bin["bin_id"],
                        "cluster_words": high_bin["tokens"],
                        "target_index": high_nibble,
                        "bits": 4,
                        "encoding_type": "high_nibble",
                        "byte_index": byte_index,
                    },
                    {
                        "nibble_value": low_nibble,
                        "cluster_id": low_bin["bin_id"],
                        "cluster_words": low_bin["tokens"],
                        "target_index": low_nibble,
                        "bits": 4,
                        "encoding_type": "low_nibble",
                        "byte_index": byte_index,
                    },
                ]

        return None

    def _choose_chunking_params(self, choices: List[Dict]) -> Tuple[int, int]:
        # Lowered from the legacy 96/128-bit chunks (~24 forced tokens each)
        # to a configurable, much smaller default. Fewer forced tokens per
        # chunk gives the LLM room to weave them into natural prose, which
        # collapses the perplexity-spike signature picked up by GPT-2 PPL.
        if not choices:
            return self.target_bits_per_chunk, self.max_choices_per_chunk

        # Both nibble and byte choices honour the same target; the legacy
        # split (96 vs 128) only existed to bias capacity per chunk.
        return self.target_bits_per_chunk, self.max_choices_per_chunk

    def _byte_chunking(
        self,
        choices: List[Dict],
        target_bits_per_chunk: int = 96,
        max_choices_per_chunk: Optional[int] = None,
    ) -> List[List[Dict]]:
        chunks: List[List[Dict]] = []
        current_chunk: List[Dict] = []
        current_bits = 0

        for choice in choices:
            current_chunk.append(choice)
            current_bits += choice.get("bits", 1)

            hit_bit_target = current_bits >= target_bits_per_chunk
            hit_choice_target = (
                max_choices_per_chunk is not None
                and len(current_chunk) >= max_choices_per_chunk
            )

            if hit_bit_target or hit_choice_target:
                chunks.append(current_chunk)
                current_chunk = []
                current_bits = 0

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _tokenize_for_matching(self, text: str) -> List[str]:
        return [t.lower() for t in self.TOKEN_RE.findall(text)]

    def _required_words_in_order(self, tokens: List[str], required_words: List[str]) -> bool:
        idx = -1
        for word in required_words:
            word_lower = word.lower()
            try:
                idx = tokens.index(word_lower, idx + 1)
            except ValueError:
                return False
        return True

    def _get_required_words(self, choices: List[Dict]) -> List[str]:
        required_words: List[str] = []
        for choice in choices:
            cluster_words = choice.get("cluster_words", [])
            target_index = choice.get("target_index", 0)
            if cluster_words and 0 <= target_index < len(cluster_words):
                required_words.append(cluster_words[target_index])
        return required_words

    def _is_code_like_token(self, token: str) -> bool:
        if "." in token or "_" in token:
            return True
        if re.search(r"[a-z][A-Z]", token):
            return True
        if re.search(r"[A-Z].*[a-z].*[A-Z]", token):
            return True
        return False

    def _format_required_word_for_prompt(self, word: str) -> str:
        if self._is_code_like_token(word):
            return f"`{word}`"
        return word

    def _extract_json_object_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        cleaned = re.sub(r"```json\s*", "", text)
        cleaned = re.sub(r"```\s*", "", cleaned)
        cleaned = cleaned.strip()

        candidates = [cleaned]

        start_obj = cleaned.find("{")
        end_obj = cleaned.rfind("}")
        if start_obj != -1 and end_obj != -1 and end_obj >= start_obj:
            candidates.append(cleaned[start_obj:end_obj + 1])

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue

        return None

    def _llm_validate_surface_naturalness(
        self,
        text: str,
        artifact_type_desc: str,
        required_words: List[str],
    ) -> Tuple[bool, str]:
        required_preview = ", ".join(self._format_required_word_for_prompt(w) for w in required_words[:24])

        prompt = f"""You are validating a short GitHub developer note.

Decide whether this note is natural enough to keep.

Important rules:
- Required tokens may include code identifiers, acronyms, product names, proper nouns, library names, hyphenated terms, and unusual technical strings.
- Reject the note if a clearly ordinary English word is unnecessarily capitalized in the middle of a sentence.
- Do NOT reject the note for mid-sentence capitalization when the token could reasonably be a proper noun, acronym, product name, library name, code identifier, or a required technical token.
- Do NOT reject the note just because a token is backticked, code-like, acronym-like, or technically unusual.
- Reject only if the prose itself is clearly awkward or the capitalization/wording is clearly unnatural for a short GitHub note.

Artifact type:
{artifact_type_desc}

Required tokens that may legitimately look unusual:
{required_preview}

Return ONLY valid JSON in exactly this format:
{{"ok": true, "reason": "brief reason"}}

Text:
{text}
"""

        try:
            response = client.chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT,
                messages=[
                    ChatCompletionSystemMessageParam(
                        role="system",
                        content=(
                            "You are a careful validator for short GitHub developer prose. "
                            "Be permissive with technical tokens, but treat gratuitous capitalization of ordinary words "
                            "in the middle of a sentence as a real problem. Return only strict JSON."
                        ),
                    ),
                    ChatCompletionUserMessageParam(role="user", content=prompt),
                ],
            )

            response_choices = getattr(response, "choices", None)
            if not response_choices:
                return True, "surface validator unavailable"

            first_choice = response_choices[0]
            msg = getattr(first_choice, "message", None)
            if msg is None:
                return True, "surface validator unavailable"

            raw = msg.content or ""
            if isinstance(raw, list):
                parts: List[str] = []
                for item in raw:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(item.get("text", ""))
                    elif hasattr(item, "type") and getattr(item, "type", None) == "text":
                        parts.append(getattr(item, "text", ""))
                    elif isinstance(item, str):
                        parts.append(item)
                raw = "".join(parts)

            raw = raw.strip()
            parsed = self._extract_json_object_from_text(raw)
            if not parsed:
                return True, "surface validator parse fallback"

            ok = parsed.get("ok")
            reason = str(parsed.get("reason", "")).strip()

            if isinstance(ok, bool):
                return ok, reason or ("surface accepted" if ok else "surface rejected")

            return True, "surface validator parse fallback"
        except Exception:
            return True, "surface validator unavailable"

    def _has_adjacent_duplicate_token_in_sentence(self, text: str) -> bool:
        sentence_parts = re.split(r"(?<=[.!?])\s+", text.strip())
        for sentence in sentence_parts:
            tokens = self._tokenize_for_matching(sentence)
            if any(a == b for a, b in zip(tokens, tokens[1:])):
                return True
        return False

    def _generate_byte_chunk(
        self,
        context: Dict[str, Any],
        chunk_idx: int,
        choices: List[Dict],
        used_words_global: Set[str],
        previous_stegotexts: List[str],
        message_seed: int = 0,
    ) -> Tuple[str, List[Dict]]:
        artifact_class = context.get("artifact_class") or self.ARTIFACT_CYCLE[chunk_idx % len(self.ARTIFACT_CYCLE)][0]
        is_comment = artifact_class in self.COMMENT_CLASSES
        artifact_type_desc = self.ARTIFACT_TYPE_MAP.get(artifact_class, "GitHub discussion")
        action = context.get("action", "view")

        required_words = self._get_required_words(choices)

        # Per-chunk RNG drives persona/surface-form/sampling/exemplar choices.
        # Deterministic in (message, chunk_idx) so reruns reproduce the chunk.
        chunk_rng = random.Random(self._chunk_seed(message_seed, chunk_idx))

        code_like_words = [w for w in required_words if self._is_code_like_token(w)]
        # Bias toward a fenced code block when the chunk is dominated by
        # code-like required tokens; real PR/issue text routinely uses fences.
        force_code_block = len(code_like_words) >= max(3, len(required_words) // 3)

        persona_label, persona_addendum = self._pick_persona(chunk_rng)
        surface_form = self._pick_surface_form(chunk_rng, force_code_block=force_code_block)
        exemplars = self._pick_exemplars(chunk_rng, artifact_class, k=2)
        temperature, top_p = self._sample_temperature(chunk_rng)

        prompt = self._build_byte_prompt(
            artifact_type=artifact_type_desc,
            artifact_class=artifact_class,
            action=action,
            is_comment=is_comment,
            required_words=required_words,
            previous_stegotexts=previous_stegotexts,
            context=context,
            exemplars=exemplars,
            persona_label=persona_label,
            surface_form=surface_form,
        )

        def _call_model(prompt_text: str, system_addendum: str) -> str:
            system_content = (
                "You are a GitHub user writing a short developer note. Match the style "
                "of real GitHub Issue/PR text: sometimes terse, sometimes a bullet list, "
                "sometimes a code block, sometimes a single sentence without a final period. "
                "Some required tokens may be code identifiers such as method names, dotted "
                "paths, or identifiers with underscores. Preserve those character-for-character "
                "(case, dots, underscores). Inline backticks are allowed for code-like tokens. "
                "Do not rewrite, normalize, split, or paraphrase required tokens. "
                + (system_addendum or "")
            )
            response = client.chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT,
                messages=[
                    ChatCompletionSystemMessageParam(
                        role="system",
                        content=system_content,
                    ),
                    ChatCompletionUserMessageParam(role="user", content=prompt_text),
                ],
                temperature=temperature,
                top_p=top_p,
            )

            response_choices = getattr(response, "choices", None)
            if not response_choices:
                raise RuntimeError(f"Azure OpenAI returned no choices: {response!r}")

            first_choice = response_choices[0]
            msg = getattr(first_choice, "message", None)
            if msg is None:
                raise RuntimeError(f"Azure OpenAI returned a choice without a message: {response!r}")

            text = msg.content or ""
            if isinstance(text, list):
                parts: List[str] = []
                for item in text:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(item.get("text", ""))
                    elif hasattr(item, "type") and getattr(item, "type", None) == "text":
                        parts.append(getattr(item, "text", ""))
                    elif isinstance(item, str):
                        parts.append(item)
                text = "".join(parts)

            text = text.strip()
            if not text:
                raise RuntimeError(f"Azure OpenAI returned empty content: {response!r}")

            return text

        force_period = bool(surface_form.get("force_terminal_period", True))

        def _normalize_text(t: str) -> str:
            # Collapse whitespace but preserve newlines (bullet lists / code blocks).
            t = re.sub(r"[ \t]+", " ", t).strip()
            t = re.sub(r"\n{3,}", "\n\n", t)
            if force_period and not t.endswith((".", "!", "?", "`", ")", "]")):
                t += "."
            return t

        def _missing_required_words(t: str) -> List[str]:
            tokens = self._tokenize_for_matching(t)
            token_counts = Counter(tokens)
            missing: List[str] = []
            for required in required_words:
                key = required.lower()
                if token_counts.get(key, 0) <= 0:
                    missing.append(required)
                else:
                    token_counts[key] -= 1
            return missing

        text = _normalize_text(_call_model(prompt, persona_addendum))
        positions = self._extract_byte_positions(text, choices)
        tokens = self._tokenize_for_matching(text)
        missing = _missing_required_words(text)
        order_ok = self._required_words_in_order(tokens, required_words)
        # Adjacent-duplicate gating used to be a hard reject; relaxing it (it
        # is a benign artifact in many real GitHub notes) preserves variance
        # without affecting decoding.
        has_dup = False

        surface_ok = True
        surface_reason = ""
        if (
            self.enable_surface_validator
            and not missing
            and order_ok
            and len(positions) == len(choices)
        ):
            surface_ok, surface_reason = self._llm_validate_surface_naturalness(
                text=text,
                artifact_type_desc=artifact_type_desc,
                required_words=required_words,
            )

        max_retries = 4  # lowered from 6: gentler retries reduce style monoculture
        attempts = 0
        retry_styles = [
            "Keep the prose natural for the chosen surface form. Do not over-polish.",
            "Match the rough length and shape of the style references shown above.",
            "Write the way a developer would in a real GitHub note for this artifact.",
        ]

        while (
            missing
            or not order_ok
            or len(positions) != len(choices)
            or has_dup
            or not surface_ok
        ) and attempts < max_retries:
            style_hint = retry_styles[attempts % len(retry_styles)]

            issues: List[str] = []
            if missing:
                issues.append(
                    "Missing required words: "
                    + ", ".join(self._format_required_word_for_prompt(word) for word in missing)
                )
            if not order_ok:
                issues.append("Required words were not in the exact required order.")
            if len(positions) != len(choices):
                issues.append(f"Matched positions were {len(positions)} of {len(choices)}.")
            if not surface_ok:
                issues.append(
                    "A secondary LLM validator judged the note as not natural enough"
                    + (f": {surface_reason}" if surface_reason else ".")
                )

            rewrite_prompt = (
                prompt
                + "\n\nREWRITE REQUIRED: Your previous response did not satisfy constraints."
                + "\n"
                + "\n".join(issues)
                + "\nYou must keep the REQUIRED WORDS in the exact order given. Do not reorder or skip any word."
                + "\nCode-like required tokens must be preserved exactly character-for-character."
                + "\n"
                + style_hint
                + "\nReturn only the rewritten text."
            )

            text = _normalize_text(_call_model(rewrite_prompt, persona_addendum))
            positions = self._extract_byte_positions(text, choices)
            tokens = self._tokenize_for_matching(text)
            missing = _missing_required_words(text)
            order_ok = self._required_words_in_order(tokens, required_words)
            has_dup = False

            surface_ok = True
            surface_reason = ""
            if (
                self.enable_surface_validator
                and not missing
                and order_ok
                and len(positions) == len(choices)
            ):
                surface_ok, surface_reason = self._llm_validate_surface_naturalness(
                    text=text,
                    artifact_type_desc=artifact_type_desc,
                    required_words=required_words,
                )

            attempts += 1

        if missing or not order_ok or len(positions) != len(choices) or not surface_ok:
            problems: List[str] = []
            if missing:
                problems.append(f"Missing: {', '.join(missing)}")
            if not order_ok:
                problems.append("order mismatch")
            if len(positions) != len(choices):
                problems.append(f"positions={len(positions)}/{len(choices)}")
            if not surface_ok:
                problems.append(f"surface validation: {surface_reason or 'not natural enough'}")
            raise RuntimeError(
                f"Failed to encode all required words after {max_retries} retries. "
                + "; ".join(problems)
            )

        return text, positions

    def _build_byte_prompt(
        self,
        artifact_type: str,
        artifact_class: str,
        action: str,
        is_comment: bool,
        required_words: List[str],
        previous_stegotexts: List[str],
        context: Dict[str, Any],
        exemplars: List[str],
        persona_label: str,
        surface_form: Dict[str, Any],
    ) -> str:
        # ---- 1. Optional artifact-context conditioning ----
        # Any of these keys, if present in the caller context, are surfaced to
        # the model so the generated text is about the actual artifact instead
        # of a generic "software development" prompt. All are optional.
        ctx_lines: List[str] = []
        title = (context.get("issue_title") or context.get("title") or "").strip()
        if title:
            ctx_lines.append(f"Title: {title[:200]}")
        repo_owner = (context.get("repo_owner") or "").strip()
        repo_name = (context.get("repo_name") or "").strip()
        if repo_owner and repo_name:
            ctx_lines.append(f"Repo: {repo_owner}/{repo_name}")
        repo_language = (context.get("repo_language") or "").strip()
        if repo_language:
            ctx_lines.append(f"Primary language: {repo_language}")
        file_paths = context.get("file_paths") or []
        if isinstance(file_paths, (list, tuple)) and file_paths:
            ctx_lines.append("Relevant files: " + ", ".join(str(p) for p in list(file_paths)[:5]))
        related_ids = context.get("related_identifiers") or []
        if isinstance(related_ids, (list, tuple)) and related_ids:
            ctx_lines.append("Related: " + ", ".join(str(p) for p in list(related_ids)[:5]))
        parent_text = (context.get("parent_text") or "").strip()
        if parent_text:
            ctx_lines.append("Parent excerpt: " + parent_text[:400].replace("\n", " "))

        context_block = ""
        if ctx_lines:
            context_block = "Artifact context (write something plausible for this):\n" + "\n".join(
                f"- {ln}" for ln in ctx_lines
            ) + "\n\n"

        # ---- 2. Few-shot benign exemplars ----
        # Real benign texts for the same artifact_class anchor the prompt to
        # the target distribution. Skipped silently when the corpus is absent.
        exemplar_block = ""
        if exemplars:
            ex_lines = []
            for i, ex in enumerate(exemplars):
                preview = ex.replace("\n", " ").strip()
                if len(preview) > 220:
                    preview = preview[:220].rstrip() + "..."
                ex_lines.append(f"  {i + 1}. {preview}")
            exemplar_block = (
                "Style references (real GitHub text for this artifact type — match the "
                "rough tone and length, do not copy content):\n"
                + "\n".join(ex_lines)
                + "\n\n"
            )

        # ---- 3. Repetition warning (kept, but lighter) ----
        repetition_warning = ""
        if previous_stegotexts:
            repetition_warning = (
                "Earlier generated chunks (use different wording / shape):\n"
            )
            for i, prev in enumerate(previous_stegotexts[-3:]):
                preview = prev.replace("\n", " ")
                repetition_warning += f"  {i + 1}. {preview[:100]}...\n"
            repetition_warning += "\n"

        # ---- 4. Required-words instruction ----
        required_order_list = "\n".join(
            [f"{i + 1}. {self._format_required_word_for_prompt(w)}" for i, w in enumerate(required_words)]
        )
        code_like_words = [w for w in required_words if self._is_code_like_token(w)]
        code_hint = ""
        if code_like_words:
            formatted_code_words = ", ".join(f"`{w}`" for w in code_like_words[:8])
            code_hint = (
                "\nSome REQUIRED WORDS are code-like tokens. Preserve them exactly "
                "character-for-character. Inline backticks are preferred.\n"
                f"Code-like examples in this chunk: {formatted_code_words}"
            )
        incorporate_instruction = (
            "REQUIRED WORDS (must all appear at least once, as standalone tokens, "
            "case-insensitive) IN THIS EXACT ORDER:\n"
            f"{required_order_list}\n"
            "Do not split, paraphrase, or alter required tokens. For ordinary words "
            "use normal sentence case."
        )

        # ---- 5. Surface-form variation ----
        sentence_min = int(surface_form.get("sentence_min", 2))
        sentence_max = int(surface_form.get("sentence_max", 4))
        allow_bullets = bool(surface_form.get("allow_bullets", False))
        allow_code_block = bool(surface_form.get("allow_code_block", False))
        force_period = bool(surface_form.get("force_terminal_period", True))
        sf_label = surface_form.get("label", "prose")

        format_hints: List[str] = []
        if allow_bullets:
            format_hints.append(
                "Format as a brief bullet list (3-6 items, '-' prefix). Bullets are short fragments."
            )
        elif allow_code_block:
            format_hints.append(
                "Use a small fenced ```code block``` (a few lines) plus 1-2 sentences of prose around it."
            )
        else:
            format_hints.append(
                f"Write {sentence_min}-{sentence_max} sentences as prose. No bullets, no fenced code blocks."
            )
        if not force_period:
            format_hints.append("It is fine if the note does not end in a period.")
        else:
            format_hints.append("End with a sentence-final period.")

        # ---- 6. Opening framed by action / persona ----
        if action == "comment" or is_comment:
            opening = f"Write a new {artifact_type} reply."
        elif action == "edit":
            opening = f"Write an updated {artifact_type} body or comment."
        else:
            opening = f"Write a short note that fits a {artifact_type} on the artifact above."

        # ---- 7. Assemble ----
        return f"""{opening}

{context_block}{exemplar_block}{repetition_warning}{incorporate_instruction}{code_hint}

Surface form for this chunk: {sf_label} (persona: {persona_label})
- """ + "\n- ".join(format_hints) + """

Return only the text:"""

    def _extract_byte_positions(self, text: str, choices: List[Dict]) -> List[Dict]:
        positions: List[Dict] = []
        tokens = self._tokenize_for_matching(text)
        search_start = 0

        for choice in choices:
            cluster_words = choice.get("cluster_words", [])
            target_index = choice.get("target_index", 0)

            if not cluster_words or target_index is None or target_index >= len(cluster_words):
                continue

            target_word = cluster_words[target_index]
            key = target_word.lower()

            found_position = None
            for idx in range(search_start, len(tokens)):
                if tokens[idx] == key:
                    found_position = idx
                    search_start = idx + 1
                    break

            if found_position is None:
                continue

            positions.append(
                {
                    "choice_id": choice.get("choice_id"),
                    "byte_index": choice.get("byte_index"),
                    "chosen_word": target_word,
                    "chosen_index": target_index,
                    "target_index": target_index,
                    "encoding_type": choice.get("encoding_type", "unknown"),
                    "bits": choice.get("bits", 0),
                    "token_position": found_position,
                }
            )

        return positions


class ByteLevelStegoEncoder:
    def __init__(
        self,
        bins_path: str = None,
        quiet: bool = False,
        benign_exemplars_path: Optional[str] = None,
        target_bits_per_chunk: int = DEFAULT_TARGET_BITS_PER_CHUNK,
        max_choices_per_chunk: int = DEFAULT_MAX_CHOICES_PER_CHUNK,
        enable_surface_validator: bool = False,
    ):
        self.encoder = ByteLevelSemanticEncoder(
            bins_path,
            quiet=quiet,
            benign_exemplars_path=benign_exemplars_path,
            target_bits_per_chunk=target_bits_per_chunk,
            max_choices_per_chunk=max_choices_per_chunk,
            enable_surface_validator=enable_surface_validator,
        )

    def encode(
        self,
        message: str,
        context: Dict[str, Any],
        positions_filename: Optional[str] = None,
    ) -> List[str]:
        chunks, positions_data = self.encoder.encode_message(message, context)

        if positions_filename:
            self._save_positions(positions_filename, positions_data)
        else:
            hash_val = hashlib.md5(message.encode()).hexdigest()[:6]
            self._save_positions(f"byte_positions_{hash_val}.json", positions_data)

        return chunks

    def _save_positions(self, filename: str, data: List[Dict]):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "metadata": {
                        "timestamp": datetime.now().isoformat(),
                        "encoding": "byte_level_v1",
                    },
                    "chunks": data,
                },
                f,
                indent=2,
            )

