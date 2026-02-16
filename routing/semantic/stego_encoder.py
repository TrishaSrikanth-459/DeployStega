from __future__ import annotations

import json
import os
import re
import math
from typing import Dict, Any, List, Tuple, Optional, Set
from collections import defaultdict
import random
from datetime import datetime
import hashlib
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

import openai

# ============================================================
# Configuration
# ============================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY must be set")

client = openai.OpenAI(api_key=OPENAI_API_KEY)


# ============================================================
# BYTE-LEVEL Semantic Encoder (with quiet mode)
# ============================================================

class ByteLevelSemanticEncoder:
    # Map artifact classes to natural language descriptions
    ARTIFACT_TYPE_MAP = {
        "Issue": "GitHub issue",
        "PullRequest": "pull request",
        "GitTag": "release tag",
        "Label": "label",
        "Milestone": "milestone",
        "IssueComment": "issue comment",
        "PullRequestComment": "pull request comment",
        "CommitComment": "commit comment",
        "Repository": "repository",
        "Commit": "commit",
    }

    # Artifact classes that are created as new comments (vs. editing the parent)
    COMMENT_CLASSES = {"IssueComment", "PullRequestComment", "CommitComment"}

    # Cycle of artifact types to use for different chunks
    ARTIFACT_CYCLE = [
        ("IssueComment", True),
        ("PullRequestComment", True),
        ("CommitComment", True),
        ("Issue", False),
        ("PullRequest", False),
        ("GitTag", False),
    ]

    def __init__(self, bins_path: str = "token_binning_data/bins_k16.json", quiet: bool = False):
        self.quiet = quiet
        self.bins = []
        self.large_bins = []   # 256+ words
        self.medium_bins = []  # 64-255 words
        self.small_bins = []   # 16-63 words
        self.tiny_bins = []    # 2-15 words
        self._load_byte_bins(bins_path)

        if not self.quiet:
            print(f"\n📊 BYTE-LEVEL ENCODING CAPACITY")
            print(f"  Large bins (256+ words): {len(self.large_bins)} - Byte encoding (8 bits)")
            print(f"  Medium bins (64-255): {len(self.medium_bins)} - 6-7 bit encoding")
            print(f"  Small bins (16-63 words): {len(self.small_bins)} - 4-5 bit encoding")
            print(f"  Tiny bins (2-15): {len(self.tiny_bins)} - 1-3 bit encoding")

        if len(self.large_bins) == 0 and len(self.medium_bins) == 0 and len(self.small_bins) < 2:
            raise RuntimeError(
                "No usable bins to encode. Need at least 2 bins with size>=16 "
                "(small/medium/large) to encode bytes as two nibbles."
            )

        if not self.quiet:
            if len(self.large_bins) == 0:
                print("⚠ NOTE: No 256-word bins available (no direct 8-bit/choice encoding).")
            if len(self.medium_bins) == 0:
                print("⚠ NOTE: No 64-word bins available (no 6-7 bit/choice encoding).")
            if len(self.small_bins) >= 2:
                print("✅ Using SMALL bins to encode bytes as TWO NIBBLES (4 bits + 4 bits).")

    def _load_byte_bins(self, bins_path: str):
        """Load bins."""
        if not self.quiet:
            print(f"Loading byte-level bins from {bins_path}...")

        with open(bins_path, 'r', encoding="utf-8") as f:
            data = json.load(f)

        bins_data = data['bins'] if 'bins' in data else data

        for bin_id, tokens in enumerate(bins_data):
            if len(tokens) >= 2:
                clean_tokens = [str(tok).strip() for tok in tokens if str(tok).strip()]
                size = len(clean_tokens)

                bin_info = {
                    'bin_id': bin_id,
                    'tokens': clean_tokens,
                    'size': size,
                    'capacity_bits': int(math.log2(size)) if size >= 2 else 1
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
            print(f"✓ Loaded {len(self.bins)} byte-level bins")

    def encode_message(self, message: str, context: Dict[str, Any]) -> tuple[list[Any], list[Any]]:
        """
        Encode message using the provided context.
        Returns (stegotexts, positions_data)
        """
        if not self.quiet:
            print(f"\n🔐 BYTE-LEVEL ENCODING: '{message}'")

        # Extract context fields with defaults
        artifact_class = context.get("artifact_class", "IssueComment")
        parent_text = context.get("parent_text", "")
        repo_files = context.get("repo_files", {})
        repo_context = context.get("repo_context", "authentication system")
        file_context = context.get("file_context", "")

        message_bytes = message.encode('utf-8')
        if not self.quiet:
            print(f"  Message bytes: {len(message_bytes)}")
            print(f"  Message bits: {len(message_bytes) * 8}")

        choices = self._create_byte_choices(message_bytes)
        if not self.quiet:
            print(f"  Created {len(choices)} encoding choices")

        if not choices:
            raise RuntimeError(
                "Created 0 encoding choices. This means you have no bins capable of encoding "
                "your message under the current rules. For nibble encoding you need at least "
                "2 bins with size>=16 (small/medium/large)."
            )

        bits_per_choice = sum(c.get('bits', 0) for c in choices) / len(choices)
        if not self.quiet:
            print(f"  Average bits per choice: {bits_per_choice:.1f}")

        # Group choices into larger chunks (target 64 bits per chunk)
        chunks: List[List[Dict]] = self._byte_chunking(choices, target_bits_per_chunk=64)

        stegotexts: List[str] = []
        positions_data: List[Dict[str, Any]] = []
        used_words_global: Set[str] = set()      # track words already used to avoid repetition
        previous_stegotexts: List[str] = []      # track full texts for repetition warnings

        for chunk_idx, chunk_choices in enumerate(chunks):
            if not self.quiet:
                print(f"\n  --- Chunk {chunk_idx + 1} ---")
                print(f"  Encoding {len(chunk_choices)} choices")

            # Rotate the parent text by taking a different sentence or portion
            sentences = re.split(r'(?<=[.!?])\s+', parent_text) if parent_text else [""]
            if sentences and sentences[0]:
                parent_for_chunk = sentences[chunk_idx % len(sentences)]
            else:
                parent_for_chunk = parent_text

            chunk_text, chunk_positions = self._generate_byte_chunk(
                context={
                    "artifact_class": artifact_class,
                    "parent_text": parent_for_chunk,
                    "repo_files": repo_files,
                    "repo_context": repo_context,
                    "file_context": file_context,
                },
                chunk_idx=chunk_idx,
                choices=chunk_choices,
                used_words_global=used_words_global,
                previous_stegotexts=previous_stegotexts,
            )

            if not self.quiet:
                print("\n    📝 STEGOTEXT (Chunk {0})".format(chunk_idx + 1))
                if chunk_text:
                    print("    " + chunk_text)
                else:
                    print("    (No text generated)")

            stegotexts.append(chunk_text)
            previous_stegotexts.append(chunk_text)

            chunk_bits = sum(c.get('bits', 0) for c in chunk_choices)
            positions_data.append({
                'chunk_id': chunk_idx,
                'choices': len(chunk_choices),
                'encoded_bits': chunk_bits,
                'positions': chunk_positions,
                'text_preview': chunk_text[:160] + "..." if len(chunk_text) > 160 else chunk_text
            })

            # Add the words that were actually used to the global set to avoid repetition
            for pos in chunk_positions:
                word = pos.get('chosen_word')
                if word:
                    used_words_global.add(word.lower())

            if not self.quiet:
                print(f"\n    🔎 STEGOCHUNK MAP (Chunk {chunk_idx + 1})")
                if not chunk_text:
                    print("    (No text generated)")
                else:
                    pos_by_id = {p.get("choice_id"): p for p in chunk_positions}
                    for ch in chunk_choices:
                        cid = ch.get("choice_id")
                        enc_type = ch.get("encoding_type", "unknown")
                        bits = ch.get("bits", 0)
                        target = ch.get("target_index", None)

                        if cid in pos_by_id:
                            p = pos_by_id[cid]
                            print(
                                f"    choice_id={cid:>4} | {enc_type:<11} {bits:>2}b | "
                                f"target_index={str(target):<4} | chosen_index={str(p.get('chosen_index')):<4} | "
                                f"word='{p.get('chosen_word')}'"
                            )
                        else:
                            print(
                                f"    choice_id={cid:>4} | {enc_type:<11} {bits:>2}b | "
                                f"target_index={str(target):<4} | NOT ENCODED"
                            )
                print("")

        return stegotexts, positions_data

    def _create_byte_choices(self, message_bytes: bytes) -> List[Dict]:
        """Create choices."""
        choices: List[Dict] = []

        for i, byte_value in enumerate(message_bytes):
            byte_choice = self._encode_byte(byte_value, i)
            if byte_choice is None:
                raise RuntimeError(
                    f"Byte {i} (0x{byte_value:02x}) could not be encoded with available bins.\n"
                    f"Have: large={len(self.large_bins)}, medium={len(self.medium_bins)}, small={len(self.small_bins)}, tiny={len(self.tiny_bins)}.\n"
                    f"To encode bytes you need either:\n"
                    f"  - 1 large bin (>=256) for direct byte encoding, OR\n"
                    f"  - 2 bins with size>=16 (medium/small) for nibble encoding.\n"
                    f"No synthetic fallback is enabled."
                )

            if isinstance(byte_choice, list):
                choices.extend(byte_choice)
            else:
                choices.append(byte_choice)

        for idx, ch in enumerate(choices):
            ch["choice_id"] = idx

        encoding_stats = defaultdict(int)
        for choice in choices:
            encoding_stats[choice.get('encoding_type', 'unknown')] += 1

        if not self.quiet:
            print("  Encoding distribution:")
            for enc_type, count in sorted(encoding_stats.items()):
                bits = {'byte': 8, 'high_nibble': 4, 'low_nibble': 4}.get(enc_type, 0)
                print(f"    {enc_type}: {count} choices ({bits} bits each)")

        return choices

    def _encode_byte(self, byte_value: int, byte_index: int) -> Optional[Dict | List[Dict]]:
        """Encode a byte using ONLY real bins (no synthetic fallback)."""

        # 1) Direct byte encoding with a large bin (>=256)
        if self.large_bins:
            cluster = self.large_bins[byte_index % len(self.large_bins)]
            return {
                'byte_value': byte_value,
                'cluster_id': cluster['bin_id'],
                'cluster_words': cluster['tokens'],
                'target_index': byte_value % len(cluster['tokens']),
                'bits': 8,
                'encoding_type': 'byte',
                'byte_index': byte_index
            }

        # 2) Nibble encoding with medium bins (>=64)
        if len(self.medium_bins) >= 2:
            high_nibble = (byte_value >> 4) & 0x0F
            low_nibble = byte_value & 0x0F

            high_bin = self.medium_bins[byte_index % len(self.medium_bins)]
            low_bin = self.medium_bins[(byte_index + 1) % len(self.medium_bins)]

            if len(high_bin['tokens']) >= 16 and len(low_bin['tokens']) >= 16:
                return [
                    {
                        'nibble_value': high_nibble,
                        'cluster_id': high_bin['bin_id'],
                        'cluster_words': high_bin['tokens'],
                        'target_index': high_nibble,
                        'bits': 4,
                        'encoding_type': 'high_nibble',
                        'byte_index': byte_index
                    },
                    {
                        'nibble_value': low_nibble,
                        'cluster_id': low_bin['bin_id'],
                        'cluster_words': low_bin['tokens'],
                        'target_index': low_nibble,
                        'bits': 4,
                        'encoding_type': 'low_nibble',
                        'byte_index': byte_index
                    }
                ]

        # 3) Nibble encoding with SMALL bins (>=16)
        if len(self.small_bins) >= 2:
            high_nibble = (byte_value >> 4) & 0x0F
            low_nibble = byte_value & 0x0F

            high_bin = self.small_bins[byte_index % len(self.small_bins)]
            low_bin = self.small_bins[(byte_index + 1) % len(self.small_bins)]

            if len(high_bin['tokens']) >= 16 and len(low_bin['tokens']) >= 16:
                return [
                    {
                        'nibble_value': high_nibble,
                        'cluster_id': high_bin['bin_id'],
                        'cluster_words': high_bin['tokens'],
                        'target_index': high_nibble,
                        'bits': 4,
                        'encoding_type': 'high_nibble',
                        'byte_index': byte_index
                    },
                    {
                        'nibble_value': low_nibble,
                        'cluster_id': low_bin['bin_id'],
                        'cluster_words': low_bin['tokens'],
                        'target_index': low_nibble,
                        'bits': 4,
                        'encoding_type': 'low_nibble',
                        'byte_index': byte_index
                    }
                ]

        return None

    def _byte_chunking(self, choices: List[Dict], target_bits_per_chunk: int = 64) -> List[List[Dict]]:
        """Group choices into chunks of at least target_bits_per_chunk bits."""
        chunks: List[List[Dict]] = []
        current_chunk: List[Dict] = []
        current_bits = 0

        for choice in choices:
            current_chunk.append(choice)
            current_bits += choice.get('bits', 1)

            if current_bits >= target_bits_per_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_bits = 0

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _generate_byte_chunk(self, context: Dict[str, Any],
                             chunk_idx: int,
                             choices: List[Dict],
                             used_words_global: Set[str],
                             previous_stegotexts: List[str]) -> Tuple[str, List[Dict]]:
        """Generate natural text for encoding, with variety and avoiding repetition."""
        # Cycle through artifact types based on chunk index
        artifact_class, is_comment = self.ARTIFACT_CYCLE[chunk_idx % len(self.ARTIFACT_CYCLE)]
        artifact_type_desc = self.ARTIFACT_TYPE_MAP.get(artifact_class, "GitHub discussion")

        parent_text = context.get("parent_text", "")
        repo_files = context.get("repo_files", {})
        repo_context = context.get("repo_context", "authentication system")

        prompt = self._build_byte_prompt(
            artifact_type=artifact_type_desc,
            is_comment=is_comment,
            parent_text=parent_text,
            repo_files=repo_files,
            repo_context=repo_context,
            choices=choices,
            used_words_global=used_words_global,
            previous_stegotexts=previous_stegotexts,
        )

        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    ChatCompletionSystemMessageParam(
                        role="system",
                        content="You are a technical writer on GitHub. Write naturally and professionally, using proper English casing. Words from the provided list may be capitalized in the list, but you should lowercase them when they appear mid‑sentence unless they are proper nouns or acronyms that should remain uppercase. For example, 'Blueprint' should become 'blueprint' in the middle of a sentence."
                    ),
                    ChatCompletionUserMessageParam(
                        role="user",
                        content=prompt
                    )
                ],
                temperature=0.8,
                max_tokens=300,
                top_p=0.9
            )

            text = response.choices[0].message.content.strip()
            text = re.sub(r'\s+', ' ', text)

            if not text.endswith(('.', '!', '?')):
                text += '.'

            if not self.quiet:
                print(f"    Generated {len(text.split())} words")

            positions = self._extract_byte_positions(text, choices)

            encoded = len(positions)
            total = len(choices)
            success = encoded / total * 100 if total > 0 else 0

            if not self.quiet:
                print(f"    Encoded {encoded}/{total} choices ({success:.0f}%)")

            return text, positions

        except Exception as e:
            if not self.quiet:
                print(f"    ⚠ Error: {e}")
            return "", []

    def _build_byte_prompt(self, artifact_type: str, is_comment: bool,
                           parent_text: str, repo_files: Dict[str, str],
                           repo_context: str, choices: List[Dict],
                           used_words_global: Set[str],
                           previous_stegotexts: List[str]) -> str:
        """
        Build a prompt that asks the LLM to generate realistic content.
        - Suggests up to 10 sample words from bins, excluding already used words.
        - Allows only case changes (lowercase/uppercase) for natural flow – no other modifications.
        - Explicitly encourages lowercasing bin words mid‑sentence.
        - Explicitly allows mentioning existing files, forbids inventing new ones.
        - Uses a generic repository summary (no explicit file list) to avoid bias.
        """
        # Gather all bin words from all choices (for variety)
        all_bin_words = []
        for choice in choices:
            cluster_words = choice.get('cluster_words', [])
            all_bin_words.extend(cluster_words)

        # Remove duplicates
        unique_candidates = list(dict.fromkeys(all_bin_words))
        random.shuffle(unique_candidates)

        sample_words: List[str] = []
        for word in unique_candidates:
            word_lower = word.lower()
            if word_lower not in used_words_global and word not in sample_words:
                sample_words.append(word)
                if len(sample_words) >= 10:
                    break

        if not sample_words:
            # Fallback: take any words (should rarely happen)
            sample_words = unique_candidates[:6]

        display_words = ', '.join(sample_words)

        # Generic repository summary (no file list – the LLM already knows the repo via system prompt)
        repo_summary = "The repository contains source code and documentation relevant to the project.\n"

        # Truncate parent text if too long
        if len(parent_text) > 300:
            parent_preview = parent_text[:300] + "..."
        else:
            parent_preview = parent_text

        # Build a list of forbidden words (recently used)
        forbidden_list = list(used_words_global)[-15:] if used_words_global else []
        forbidden_str = ", ".join(forbidden_list) if forbidden_list else "none yet"

        # Repetition warning with examples
        repetition_warning = ""
        if previous_stegotexts:
            repetition_warning = (
                f"\nIMPORTANT: The following comments have already been posted. "
                f"Do NOT use the same words, phrases, or ideas. Be completely fresh.\n"
                f"Words already used (do not reuse): {forbidden_str}\n"
                f"Previous comments:\n"
            )
            for i, prev in enumerate(previous_stegotexts[-3:]):
                repetition_warning += f"  {i+1}. {prev[:100]}...\n"
            repetition_warning += "\n"

        # Instruction to incorporate sample words – strongly encourage lowercasing
        incorporate_instruction = (
            f"As you write, naturally incorporate some of these words where they fit best: {display_words}\n"
            "You may change the case of the words to fit grammatically (e.g., lowercase a capitalized word in the middle of a sentence). "
            "In fact, you should **lowercase** them unless they are proper nouns or acronyms that should remain uppercase. "
            "For example, if the word is 'Blueprint', you can write 'blueprint'.\n"
            "You may mention specific files or artifacts that exist in the repository, but do NOT invent any files or content that do not exist."
        )

        if is_comment:
            if parent_preview:
                prompt = f"""{repo_summary}{repetition_warning}Write a new {artifact_type} replying to the following content:

--- Original {artifact_type} ---
{parent_preview}
---

Be concise and natural (3-4 sentences). The reply should be about {repo_context}.

{incorporate_instruction}

CRITICAL: Do NOT repeat any words from the forbidden list. Use fresh vocabulary.

Write the reply:"""
            else:
                prompt = f"""{repo_summary}{repetition_warning}Write a new {artifact_type} about {repo_context}.

Be concise and natural (3-4 sentences).

{incorporate_instruction}

CRITICAL: Do NOT repeat any words from the forbidden list. Use fresh vocabulary.

Write naturally:"""
        else:
            if parent_preview:
                prompt = f"""{repo_summary}{repetition_warning}You need to rewrite the following {artifact_type}:

--- Original {artifact_type} ---
{parent_preview}
---

The revised version should be about {repo_context} and must naturally incorporate some of these words: {display_words}

Important guidelines:
- Keep the same general meaning and tone.
- Do not just add the words artificially; blend them in so the text reads naturally.
- You may change the case of the words to fit grammatically (e.g., lowercase a capitalized word mid‑sentence). In fact, you should **lowercase** them unless they are proper nouns or acronyms.
- You may mention specific files or artifacts that exist in the repository, but do NOT invent any files or content that do not exist.
- CRITICAL: Do NOT repeat any words from the forbidden list. Use entirely fresh language.
- Output only the rewritten {artifact_type} (no extra commentary)."""
            else:
                prompt = f"""{repo_summary}{repetition_warning}Write a {artifact_type} about {repo_context}.

Be concise and natural (3-4 sentences).

{incorporate_instruction}

CRITICAL: Do NOT repeat any words from the forbidden list. Use fresh vocabulary.

Write the {artifact_type}:"""

        return prompt

    def _extract_byte_positions(self, text: str, choices: List[Dict]) -> List[Dict]:
        """Extract which words were chosen."""
        positions: List[Dict] = []
        text_lower = text.lower()
        words = text.split()

        for choice in choices:
            found_word = None
            found_index = None

            cluster_words = choice.get('cluster_words', [])
            for idx, word in enumerate(cluster_words):
                if re.search(rf'\b{re.escape(word.lower())}\b', text_lower):
                    found_word = word
                    found_index = idx
                    break

            if found_word:
                for w in words:
                    if w.lower().strip('.,!?;:') == found_word.lower():
                        positions.append({
                            'choice_id': choice.get('choice_id'),
                            'chosen_word': found_word,
                            'chosen_index': found_index,
                            'target_index': choice.get('target_index', 0),
                            'encoding_type': choice.get('encoding_type', 'unknown'),
                            'bits': choice.get('bits', 0)
                        })
                        break

        return positions


# ============================================================
# Byte-Level Main Encoder (wrapper for routing system)
# ============================================================

class ByteLevelStegoEncoder:
    def __init__(self, bins_path: str = "token_binning_data/bins_k16.json", quiet: bool = False):
        self.encoder = ByteLevelSemanticEncoder(bins_path, quiet=quiet)

    def encode(self, message: str, context: Dict[str, Any],
               positions_filename: Optional[str] = None) -> List[str]:
        """
        Encode a secret message into stegotext chunks.

        context must contain:
          - artifact_class : str
          - parent_text    : str (original content of the artifact being used)
          - repo_files     : Dict[str, str] (optional, from grounding index)
          - repo_context   : str (optional)
          - file_context   : str (optional)
        """
        if not self.encoder.quiet:
            print(f"\n📤 BYTE-LEVEL ENCODING: '{message}'")
            print(f"  Length: {len(message)} chars = {len(message.encode('utf-8'))} bytes")
            print(f"  Artifact class: {context.get('artifact_class', 'unknown')}")
            print(f"  Parent text length: {len(context.get('parent_text', ''))} chars")
            print(f"  Repository files available: {len(context.get('repo_files', {}))}")

        chunks, positions_data = self.encoder.encode_message(message, context)

        total_bits = sum(chunk.get('encoded_bits', 0) for chunk in positions_data)
        message_bytes = len(message.encode('utf-8'))
        message_bits = message_bytes * 8

        if not self.encoder.quiet:
            print(f"\n📊 BYTE-LEVEL RESULTS")
            print(f"  Message: {message_bytes} bytes ({message_bits} bits)")
            print(f"  Encoded bits: {total_bits}")
            print(f"  Chunks generated: {len(chunks)}")
            print(f"  Bits per chunk: {total_bits / len(chunks) if chunks else 0:.1f}")
            print(f"  Efficiency: {total_bits / message_bits * 100:.1f}%")

            original_chunks = message_bytes * 2
            new_chunks = len(chunks)
            reduction = (original_chunks - new_chunks) / original_chunks * 100 if original_chunks > 0 else 0

            print(f"\n🎯 IMPROVEMENT:")
            print(f"  Original system (bit-level): ~{original_chunks} chunks")
            print(f"  Byte-level system: {new_chunks} chunks")
            print(f"  Reduction: {reduction:.0f}%")

        if positions_filename:
            self._save_positions(positions_filename, positions_data)
        else:
            hash_val = hashlib.md5(message.encode()).hexdigest()[:6]
            self._save_positions(f"byte_positions_{hash_val}.json", positions_data)

        return chunks

    def _save_positions(self, filename: str, data: List[Dict]):
        try:
            with open(filename, 'w', encoding="utf-8") as f:
                json.dump({
                    'metadata': {
                        'timestamp': datetime.now().isoformat(),
                        'encoding': 'byte_level_v1'
                    },
                    'chunks': data
                }, f, indent=2)
            if not self.encoder.quiet:
                print(f"✓ Positions saved: {filename}")
        except Exception as e:
            if not self.encoder.quiet:
                print(f"⚠ Could not save: {e}")
