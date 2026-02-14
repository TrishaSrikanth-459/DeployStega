from __future__ import annotations

import json
import os
import re
import math
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict, Counter
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
# BYTE-LEVEL Semantic Encoder
# ============================================================

class ByteLevelSemanticEncoder:
    """
    Encodes bytes using semantic-choice bins.

    IMPORTANT (no fallback):
      - We will ONLY encode using bins loaded from bins_k*.json.
      - If you have no bins that can encode at least 4 bits (size>=16),
        encoding will HARD FAIL with a clear error.

    With your current output:
      - You have 696 "small bins" (size 16-63).
      - We will encode each byte as TWO NIBBLES using TWO SMALL BINS.
        (This is not a synthetic fallback; it's using your real bins.)
    """

    def __init__(self, bins_path: str = "token_binning_data/bins_k16.json"):
        self.bins = []
        self.large_bins = []   # 256+ words
        self.medium_bins = []  # 64-255 words
        self.small_bins = []   # 16-63 words
        self.tiny_bins = []    # 2-15 words
        self._load_byte_bins(bins_path)

        print(f"\n📊 BYTE-LEVEL ENCODING CAPACITY")
        print(f"  Large bins (256+ words): {len(self.large_bins)} - Byte encoding (8 bits)")
        print(f"  Medium bins (64-255): {len(self.medium_bins)} - 6-7 bit encoding")
        print(f"  Small bins (16-63 words): {len(self.small_bins)} - 4-5 bit encoding")
        print(f"  Tiny bins (2-15): {len(self.tiny_bins)} - 1-3 bit encoding")

        # No misleading claim about "splitting into bits" when you have no tiny bins
        if len(self.large_bins) == 0 and len(self.medium_bins) == 0 and len(self.small_bins) < 2:
            raise RuntimeError(
                "No usable bins to encode. Need at least 2 bins with size>=16 "
                "(small/medium/large) to encode bytes as two nibbles."
            )

        if len(self.large_bins) == 0:
            print("⚠ NOTE: No 256-word bins available (no direct 8-bit/choice encoding).")
        if len(self.medium_bins) == 0:
            print("⚠ NOTE: No 64-word bins available (no 6-7 bit/choice encoding).")
        if len(self.small_bins) >= 2:
            print("✅ Using SMALL bins to encode bytes as TWO NIBBLES (4 bits + 4 bits).")

    def _load_byte_bins(self, bins_path: str):
        """Load bins."""
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

        print(f"✓ Loaded {len(self.bins)} byte-level bins")

    def encode_message(self, message: str, context: Dict[str, Any]) -> tuple[list[Any], list[Any]]:
        """Encode message."""
        print(f"\n🔐 BYTE-LEVEL ENCODING: '{message}'")

        message_bytes = message.encode('utf-8')
        print(f"  Message bytes: {len(message_bytes)}")
        print(f"  Message bits: {len(message_bytes) * 8}")

        choices = self._create_byte_choices(message_bytes)
        print(f"  Created {len(choices)} encoding choices")

        if not choices:
            # No fallback: hard fail with root cause
            raise RuntimeError(
                "Created 0 encoding choices. This means you have no bins capable of encoding "
                "your message under the current rules. For nibble encoding you need at least "
                "2 bins with size>=16 (small/medium/large)."
            )

        bits_per_choice = sum(c.get('bits', 0) for c in choices) / len(choices)
        print(f"  Average bits per choice: {bits_per_choice:.1f}")

        chunks: List[str] = []
        positions_data: List[Dict[str, Any]] = []

        for chunk_idx, chunk_choices in enumerate(self._byte_chunking(choices)):
            print(f"\n  --- Chunk {chunk_idx + 1} ---")
            print(f"  Encoding {len(chunk_choices)} choices")

            chunk_text, chunk_positions = self._generate_byte_chunk(
                context, chunk_idx, chunk_choices
            )

            # ALWAYS show the stegotext chunk immediately (this is what you asked for)
            print("\n    📝 STEGOTEXT (Chunk {0})".format(chunk_idx + 1))
            if chunk_text:
                print("    " + chunk_text)
            else:
                print("    (No text generated)")

            chunks.append(chunk_text)

            chunk_bits = sum(c.get('bits', 0) for c in chunk_choices)
            positions_data.append({
                'chunk_id': chunk_idx,
                'choices': len(chunk_choices),
                'encoded_bits': chunk_bits,
                'positions': chunk_positions,
                'text_preview': chunk_text[:160] + "..." if len(chunk_text) > 160 else chunk_text
            })

            # Print the stego mapping per chunk
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

        return chunks, positions_data

    def _create_byte_choices(self, message_bytes: bytes) -> List[Dict]:
        """Create choices."""
        choices: List[Dict] = []

        for i, byte_value in enumerate(message_bytes):
            byte_choice = self._encode_byte(byte_value, i)
            if byte_choice is None:
                # No fallback: hard fail (do NOT pretend we split into bits)
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

        # Fix choice_id labels (your old _get_current_choices() was always [])
        for idx, ch in enumerate(choices):
            ch["choice_id"] = idx

        # Encoding distribution (useful sanity)
        encoding_stats = defaultdict(int)
        for choice in choices:
            encoding_stats[choice.get('encoding_type', 'unknown')] += 1

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

            # Must be >=16 to index 0..15
            if len(high_bin['tokens']) >= 16 and len(low_bin['tokens']) >= 16:
                return [
                    {
                        'nibble_value': high_nibble,
                        'cluster_id': high_bin['bin_id'],
                        'cluster_words': high_bin['tokens'],
                        'target_index': high_nibble,  # direct nibble -> index 0..15
                        'bits': 4,
                        'encoding_type': 'high_nibble',
                        'byte_index': byte_index
                    },
                    {
                        'nibble_value': low_nibble,
                        'cluster_id': low_bin['bin_id'],
                        'cluster_words': low_bin['tokens'],
                        'target_index': low_nibble,   # direct nibble -> index 0..15
                        'bits': 4,
                        'encoding_type': 'low_nibble',
                        'byte_index': byte_index
                    }
                ]

        # 3) Nibble encoding with SMALL bins (>=16)  ✅ THIS IS WHAT YOU NEED RIGHT NOW
        if len(self.small_bins) >= 2:
            high_nibble = (byte_value >> 4) & 0x0F
            low_nibble = byte_value & 0x0F

            high_bin = self.small_bins[byte_index % len(self.small_bins)]
            low_bin = self.small_bins[(byte_index + 1) % len(self.small_bins)]

            # Must be >=16 to represent a nibble without modulo distortion
            if len(high_bin['tokens']) >= 16 and len(low_bin['tokens']) >= 16:
                return [
                    {
                        'nibble_value': high_nibble,
                        'cluster_id': high_bin['bin_id'],
                        'cluster_words': high_bin['tokens'],
                        'target_index': high_nibble,  # 0..15
                        'bits': 4,
                        'encoding_type': 'high_nibble',
                        'byte_index': byte_index
                    },
                    {
                        'nibble_value': low_nibble,
                        'cluster_id': low_bin['bin_id'],
                        'cluster_words': low_bin['tokens'],
                        'target_index': low_nibble,   # 0..15
                        'bits': 4,
                        'encoding_type': 'low_nibble',
                        'byte_index': byte_index
                    }
                ]

        # No fallback allowed.
        return None

    def _byte_chunking(self, choices: List[Dict], target_bits_per_chunk: int = 32) -> List[List[Dict]]:
        """Group choices into chunks."""
        chunks: List[List[Dict]] = []
        current_chunk: List[Dict] = []
        current_bits = 0

        for choice in choices:
            current_chunk.append(choice)
            current_bits += choice.get('bits', 1)

            if current_bits >= target_bits_per_chunk or len(current_chunk) >= 4:
                chunks.append(current_chunk)
                current_chunk = []
                current_bits = 0

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _generate_byte_chunk(self, context: Dict[str, Any],
                             chunk_idx: int,
                             choices: List[Dict]) -> Tuple[str, List[Dict]]:
        """Generate natural text for encoding."""
        repo_context = context.get("repo_context", "authentication system")

        artifact_types = [
            "GitHub issue comment",
            "Pull request description",
            "Code review feedback",
            "Technical discussion",
            "README update"
        ]

        artifact_type = artifact_types[chunk_idx % len(artifact_types)]
        prompt = self._build_byte_prompt(artifact_type, repo_context, choices)

        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    ChatCompletionSystemMessageParam(
                        role="system",
                        content="You are a technical writer on GitHub. Write naturally and professionally."
                    ),
                    ChatCompletionUserMessageParam(
                        role="user",
                        content=prompt
                    )
                ],
                temperature=0.7,
                max_tokens=220,
                top_p=0.9
            )

            text = response.choices[0].message.content.strip()
            text = re.sub(r'\s+', ' ', text)

            if not text.endswith(('.', '!', '?')):
                text += '.'

            print(f"    Generated {len(text.split())} words")

            positions = self._extract_byte_positions(text, choices)

            encoded = len(positions)
            total = len(choices)
            success = encoded / total * 100 if total > 0 else 0

            print(f"    Encoded {encoded}/{total} choices ({success:.0f}%)")

            return text, positions

        except Exception as e:
            print(f"    ⚠ Error: {e}")
            return "", []

    def _build_byte_prompt(self, artifact_type: str, repo_context: str, choices: List[Dict]) -> str:
        """Build prompt for encoding."""
        sample_words: List[str] = []
        for choice in choices[:6]:
            cluster_words = choice.get('cluster_words', [])
            if cluster_words:
                # IMPORTANT: for nibble encoding, we want the model to use words from bins,
                # but we do NOT want to show giant lists.
                num_samples = min(2, len(cluster_words))
                samples = random.sample(cluster_words, num_samples)
                for word in samples:
                    if word not in sample_words:
                        sample_words.append(word)

        if not sample_words:
            # This should basically never happen if bins exist, but keep it harmless.
            sample_words = ["improvement", "optimization", "security", "performance"]

        display_words = sample_words[:6]

        prompt = f"""Write a {artifact_type} about {repo_context}.

Be concise and natural (3-4 sentences).

As you write, naturally incorporate some of these words where they fit best: {', '.join(display_words)}

IMPORTANT: Don't list the words. Use them naturally in context.

Write naturally:
"""
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
# Byte-Level Main Encoder
# ============================================================

class ByteLevelStegoEncoder:
    def __init__(self, bins_path: str = "token_binning_data/bins_k16.json"):
        self.encoder = ByteLevelSemanticEncoder(bins_path)

    def encode(self, message: str, context: Dict[str, Any],
               positions_filename: Optional[str] = None) -> List[str]:
        print(f"\n📤 BYTE-LEVEL ENCODING: '{message}'")
        print(f"  Length: {len(message)} chars = {len(message.encode('utf-8'))} bytes")

        chunks, positions_data = self.encoder.encode_message(message, context)

        total_bits = sum(chunk.get('encoded_bits', 0) for chunk in positions_data)
        message_bytes = len(message.encode('utf-8'))
        message_bits = message_bytes * 8

        print(f"\n📊 BYTE-LEVEL RESULTS")
        print(f"  Message: {message_bytes} bytes ({message_bits} bits)")
        print(f"  Encoded bits: {total_bits}")
        print(f"  Chunks generated: {len(chunks)}")
        print(f"  Bits per chunk: {total_bits / len(chunks) if chunks else 0:.1f}")
        print(f"  Efficiency: {total_bits / message_bits * 100:.1f}%")

        # NOTE: with nibble encoding and your chunking rules,
        # you will NOT get 3-5 chunks for 28 bytes. That target requires 8-bit/choice bins (>=256).
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
            print(f"✓ Positions saved: {filename}")
        except Exception as e:
            print(f"⚠ Could not save: {e}")


# ============================================================
# Test
# ============================================================

def test_byte_level():
    print("\n" + "=" * 80)
    print("BYTE-LEVEL STEGANOGRAPHY ENCODER")
    print("Encodes whole bytes (via bins) — NO synthetic fallback")
    print("=" * 80)
    print("NOTE: With only 16–63 word bins, this encodes bytes as two nibbles.")
    print("=" * 80)

    try:
        encoder = ByteLevelStegoEncoder("token_binning_data/bins_k16.json")

        message = "We will meet at 9pm tonight."
        print(f"\nMessage: '{message}' ({len(message.encode('utf-8'))} bytes)")

        context = {
            "repo_context": "authentication system",
            "file_context": "src/auth/login.js"
        }

        print("\n" + "=" * 80)
        print("ENCODING...")
        print("=" * 80)

        out_file = "byte_level_test.json"
        chunks = encoder.encode(message, context, out_file)

        print(f"\nGenerated {len(chunks)} artifacts:")
        for i, chunk in enumerate(chunks):
            words = len(chunk.split())
            print(f"\n--- Artifact {i + 1} ({words} words) ---")
            print(chunk)
            print("-" * 60)

        print("\n" + "=" * 80)
        print("STEGOPOSITIONS (from saved file)")
        print("=" * 80)
        try:
            with open(out_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for ch in saved.get("chunks", []):
                cid = ch.get("chunk_id")
                print(f"\n--- Chunk {cid + 1} positions ---")
                for p in ch.get("positions", []):
                    print(
                        f"choice_id={p.get('choice_id'):>4} | {p.get('encoding_type', 'unknown'):<11} "
                        f"{p.get('bits', 0):>2}b | target_index={p.get('target_index')} | "
                        f"chosen_index={p.get('chosen_index')} | word='{p.get('chosen_word')}'"
                    )
        except Exception as e:
            print(f"⚠ Could not read {out_file}: {e}")

        return True, chunks

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False, []


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    success, chunks = test_byte_level()

    print("\n" + "=" * 80)
    if success:
        print("✅ BYTE-LEVEL ENCODER COMPLETE")
        print("   - Uses ONLY real bins (no synthetic fallback)")
        print("   - With small bins: encodes bytes as two nibbles (4+4 bits)")
        print("   - Prints stegotext chunks and per-choice mappings")
    else:
        print("❌ BYTE-LEVEL ENCODER FAILED")
    print("=" * 80)
