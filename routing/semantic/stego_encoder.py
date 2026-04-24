from __future__ import annotations

import json
import os
import re
import math
from typing import Dict, Any, List, Tuple, Optional, Set
from collections import Counter
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

    def __init__(self, bins_path: str = None, quiet: bool = False):
        self.quiet = quiet
        self.bins = []
        self.large_bins = []
        self.medium_bins = []
        self.small_bins = []
        self.tiny_bins = []

        base_dir = os.path.dirname(os.path.abspath(__file__))
        fixed_bins_path = os.path.join(base_dir, "../../token_binning_data/bins_k16.json")
        self._load_byte_bins(fixed_bins_path)

        if not self.quiet:
            print("\nBYTE-LEVEL ENCODING CAPACITY")
            print(f"  Large bins (256+ words): {len(self.large_bins)}")
            print(f"  Medium bins (64-255 words): {len(self.medium_bins)}")
            print(f"  Small bins (16-63 words): {len(self.small_bins)}")
            print(f"  Tiny bins (2-15 words): {len(self.tiny_bins)}")

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

        for chunk_idx, chunk_choices in enumerate(chunks):
            if not self.quiet:
                print(f"\n  --- Chunk {chunk_idx + 1} ---")
                print(f"  Encoding {len(chunk_choices)} choices")

            chunk_text, chunk_positions = self._generate_byte_chunk(
                context={
                    "artifact_class": context.get("artifact_class", "IssueComment"),
                    "action": context.get("action", "view"),
                },
                chunk_idx=chunk_idx,
                choices=chunk_choices,
                used_words_global=used_words_global,
                previous_stegotexts=previous_stegotexts,
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
        if not choices:
            return 64, 16

        avg_bits = sum(choice.get("bits", 0) for choice in choices) / len(choices)
        all_nibbles = all(choice.get("bits", 0) <= 4 for choice in choices)

        if all_nibbles or avg_bits <= 4.1:
            return 96, 24

        return 128, 16

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
    ) -> Tuple[str, List[Dict]]:
        artifact_class = context.get("artifact_class") or self.ARTIFACT_CYCLE[chunk_idx % len(self.ARTIFACT_CYCLE)][0]
        is_comment = artifact_class in self.COMMENT_CLASSES
        artifact_type_desc = self.ARTIFACT_TYPE_MAP.get(artifact_class, "GitHub discussion")
        action = context.get("action", "view")

        required_words = self._get_required_words(choices)

        prompt = self._build_byte_prompt(
            artifact_type=artifact_type_desc,
            action=action,
            is_comment=is_comment,
            required_words=required_words,
            previous_stegotexts=previous_stegotexts,
        )

        def _call_model(prompt_text: str) -> str:
            response = client.chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT,
                messages=[
                    ChatCompletionSystemMessageParam(
                        role="system",
                        content=(
                            "You are a GitHub user writing a short, natural developer note. "
                            "Write concise, human-sounding prose with one coherent technical theme. "
                            "Keep the note brief and avoid verbosity, laundry lists, and abrupt topic changes. "
                            "Use standard sentence case. Do not introduce capitalized ordinary words in the middle "
                            "of a sentence. Do not repeat the same word consecutively within a sentence. "
                            "Some required tokens may be code identifiers such as method names, dotted paths, "
                            "or identifiers with underscores. When a required token looks like code, preserve it "
                            "character-for-character exactly, including uppercase/lowercase letters, periods, and underscores. "
                            "For code-like required tokens, inline backticks are allowed and preferred. "
                            "Do not rewrite, normalize, split, or paraphrase required tokens."
                        ),
                    ),
                    ChatCompletionUserMessageParam(role="user", content=prompt_text),
                ],
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

        def _normalize_text(t: str) -> str:
            t = re.sub(r"\s+", " ", t).strip()
            if not t.endswith((".", "!", "?")):
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

        text = _normalize_text(_call_model(prompt))
        positions = self._extract_byte_positions(text, choices)
        tokens = self._tokenize_for_matching(text)
        missing = _missing_required_words(text)
        order_ok = self._required_words_in_order(tokens, required_words)
        has_dup = self._has_adjacent_duplicate_token_in_sentence(text)

        surface_ok = True
        surface_reason = ""
        if not missing and order_ok and len(positions) == len(choices) and not has_dup:
            surface_ok, surface_reason = self._llm_validate_surface_naturalness(
                text=text,
                artifact_type_desc=artifact_type_desc,
                required_words=required_words,
            )

        max_retries = 6
        attempts = 0
        retry_styles = [
            "Write one coherent developer note with a single technical theme.",
            "Write a compact GitHub-style note that reads naturally.",
            "Use 3-5 fluent sentences and keep the ideas connected.",
            "Write a short technical update with clear cause-and-effect between sentences.",
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
            if has_dup:
                issues.append("There was a duplicate consecutive word inside a sentence.")
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
                + "\nKeep the result concise, natural, and focused on one coherent technical theme."
                + "\nDo not use bullet points, checklist formatting, or fragment lists."
                + "\nUse normal sentence case unless a required token is naturally capitalized."
                + "\nDo not repeat the same word consecutively inside a sentence."
                + "\n"
                + style_hint
                + "\nReturn only the rewritten text."
            )

            text = _normalize_text(_call_model(rewrite_prompt))
            positions = self._extract_byte_positions(text, choices)
            tokens = self._tokenize_for_matching(text)
            missing = _missing_required_words(text)
            order_ok = self._required_words_in_order(tokens, required_words)
            has_dup = self._has_adjacent_duplicate_token_in_sentence(text)

            surface_ok = True
            surface_reason = ""
            if not missing and order_ok and len(positions) == len(choices) and not has_dup:
                surface_ok, surface_reason = self._llm_validate_surface_naturalness(
                    text=text,
                    artifact_type_desc=artifact_type_desc,
                    required_words=required_words,
                )

            attempts += 1

        if missing or not order_ok or len(positions) != len(choices) or has_dup or not surface_ok:
            problems: List[str] = []
            if missing:
                problems.append(f"Missing: {', '.join(missing)}")
            if not order_ok:
                problems.append("order mismatch")
            if len(positions) != len(choices):
                problems.append(f"positions={len(positions)}/{len(choices)}")
            if has_dup:
                problems.append("duplicate consecutive word")
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
        action: str,
        is_comment: bool,
        required_words: List[str],
        previous_stegotexts: List[str],
    ) -> str:
        repetition_warning = ""
        if previous_stegotexts:
            repetition_warning = (
                "\nIMPORTANT: Previous generated texts are shown below. "
                "Avoid reusing distinctive phrases, sentence shapes, or the same overall idea. "
                "It is fine to reuse ordinary technical words when needed.\n"
                "Previous texts:\n"
            )
            for i, prev in enumerate(previous_stegotexts[-3:]):
                repetition_warning += f"  {i + 1}. {prev[:100]}...\n"
            repetition_warning += "\n"

        required_order_list = "\n".join(
            [f"{i + 1}. {self._format_required_word_for_prompt(w)}" for i, w in enumerate(required_words)]
        )

        sentence_min = 3
        sentence_max = 5 if len(required_words) <= 16 else 6

        code_like_words = [w for w in required_words if self._is_code_like_token(w)]
        code_hint = ""
        if code_like_words:
            formatted_code_words = ", ".join(f"`{w}`" for w in code_like_words[:8])
            code_hint = (
                "\nSome REQUIRED WORDS are code-like tokens. "
                "Preserve those code-like tokens exactly character-for-character. "
                "Inline backticks are allowed and preferred for code-like tokens. "
                "Do not use fenced code blocks.\n"
                f"Code-like examples in this chunk: {formatted_code_words}"
            )

        structure_hint = ""
        if len(required_words) >= 16:
            structure_hint = (
                "\nKeep the note compact and coherent around one technical theme. "
                "Avoid making it read like a laundry list of unrelated tools or APIs."
            )

        incorporate_instruction = (
            "REQUIRED WORDS (must all appear at least once, as standalone tokens, case-insensitive) "
            "IN THIS EXACT ORDER:\n"
            f"{required_order_list}\n"
            "For ordinary words, use normal sentence case and do not capitalize them in the middle "
            "of a sentence unless grammar truly requires it. "
            "For code-like tokens, preserve the exact spelling, punctuation, and casing.\n"
            "Do not split required tokens. Inline code is allowed for code-like tokens. "
            "Do not use fenced code blocks."
        )

        if action == "comment" or is_comment:
            opening = f"{repetition_warning}Write a new short {artifact_type} reply about software development."
        elif action == "edit":
            opening = f"{repetition_warning}Write a short {artifact_type} update about software development."
        else:
            opening = f"{repetition_warning}Write a short note a developer might make while reviewing a {artifact_type} about software development."

        return f"""{opening}

Write {sentence_min}-{sentence_max} concise sentences. Keep the overall output short, human, and natural. Use one coherent technical theme rather than many disconnected topics.{structure_hint}{code_hint}

{incorporate_instruction}

Additional style rules:
- Use standard sentence case.
- Do not introduce capitalized ordinary words in the middle of a sentence.
- Do not repeat the same word consecutively inside a sentence.
- Keep the prose concise and non-verbose.
- Avoid bullet points, checklist formatting, and semicolon-separated lists.

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
    def __init__(self, bins_path: str = None, quiet: bool = False):
        self.encoder = ByteLevelSemanticEncoder(bins_path, quiet=quiet)

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

