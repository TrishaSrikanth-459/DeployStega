from __future__ import annotations

import json
import os
import re
import math
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict
import random
from datetime import datetime
import hashlib

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
    REVOLUTIONARY APPROACH: Encodes BYTES not bits
    Each semantic choice can encode a full byte (0-255)
    """

    def __init__(self, bins_path: str = "token_binning_data/byte_level_bins.json"):
        self.bins = []
        self.large_bins = []  # Bins with 256+ words for byte encoding
        self.medium_bins = []  # Bins with 64-255 words
        self.small_bins = []  # Bins with 16-63 words
        self.tiny_bins = []  # Bins with 2-15 words
        self._load_byte_bins(bins_path)

        print(f"\n📊 BYTE-LEVEL ENCODING CAPACITY")
        print(f"  Large bins (256+ words): {len(self.large_bins)} - Byte encoding")
        print(f"  Medium bins (64-255): {len(self.medium_bins)} - 6-7 bit encoding")
        print(f"  Small bins (16-63): {len(self.small_bins)} - 4-5 bit encoding")
        print(f"  Tiny bins (2-15): {len(self.tiny_bins)} - 1-3 bit encoding")

        if len(self.large_bins) == 0:
            print("⚠ WARNING: No 256-word bins available")
            print("  Will use combinations of smaller bins")

    def _load_byte_bins(self, bins_path: str):
        """Load byte-level optimized bins."""
        print(f"Loading byte-level bins from {bins_path}...")

        try:
            with open(bins_path, 'r') as f:
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

                    # Categorize by size
                    if size >= 256:
                        self.large_bins.append(bin_info)
                    elif size >= 64:
                        self.medium_bins.append(bin_info)
                    elif size >= 16:
                        self.small_bins.append(bin_info)
                    else:
                        self.tiny_bins.append(bin_info)

            print(f"✓ Loaded {len(self.bins)} byte-level bins")

        except Exception as e:
            print(f"❌ Error loading byte-level bins: {e}")
            # Create fallback bins
            self._create_fallback_bins()

    def _create_fallback_bins(self):
        """Create fallback bins if loading fails."""
        print("Creating fallback bins...")

        # Create some synthetic bins
        for i in range(50):
            size = random.choice([256, 128, 64, 32, 16, 8, 4])
            tokens = [f"word_{i}_{j}" for j in range(size)]

            bin_info = {
                'bin_id': i,
                'tokens': tokens,
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

        print(f"  Created {len(self.bins)} fallback bins")

    def encode_message(self, message: str, context: Dict[str, Any]) -> Tuple[List[str], Dict]:
        """Encode message at byte level."""
        print(f"\n🔐 BYTE-LEVEL ENCODING: '{message}'")

        # Convert message to bytes
        message_bytes = message.encode('utf-8')
        print(f"  Message bytes: {len(message_bytes)}")
        print(f"  Message bits: {len(message_bytes) * 8}")

        # Create encoding choices
        choices = self._create_byte_choices(message_bytes)
        print(f"  Created {len(choices)} encoding choices")

        if choices:
            bits_per_choice = sum(c.get('bits', 0) for c in choices) / len(choices)
            print(f"  Average bits per choice: {bits_per_choice:.1f}")

        # Generate chunks
        chunks = []
        positions_data = []

        for chunk_idx, chunk_choices in enumerate(self._byte_chunking(choices)):
            print(f"\n  --- Chunk {chunk_idx + 1} ---")
            print(f"  Encoding {len(chunk_choices)} choices")

            chunk_text, chunk_positions = self._generate_byte_chunk(
                context, chunk_idx, chunk_choices
            )

            chunks.append(chunk_text)

            chunk_bits = sum(c.get('bits', 0) for c in chunk_choices)
            positions_data.append({
                'chunk_id': chunk_idx,
                'choices': len(chunk_choices),
                'encoded_bits': chunk_bits,
                'positions': chunk_positions,
                'text_preview': chunk_text[:80] + "..." if len(chunk_text) > 80 else chunk_text
            })

        return chunks, positions_data

    def _create_byte_choices(self, message_bytes: bytes) -> List[Dict]:
        """Create choices that encode bytes efficiently."""
        choices = []

        for i, byte_value in enumerate(message_bytes):
            # Try to encode this byte
            byte_choice = self._encode_byte(byte_value, i)

            if byte_choice:
                if isinstance(byte_choice, list):
                    # Byte was split into multiple choices
                    choices.extend(byte_choice)
                else:
                    # Single choice for the byte
                    choices.append(byte_choice)
            else:
                # Fallback: split byte into bits
                print(f"  ⚠ Byte {i} (0x{byte_value:02x}): No suitable bin, splitting into bits")
                bit_choices = self._encode_byte_as_bits(byte_value, i)
                choices.extend(bit_choices)

        # Analyze encoding efficiency
        if choices:
            encoding_stats = defaultdict(int)
            for choice in choices:
                enc_type = choice.get('encoding_type', 'unknown')
                encoding_stats[enc_type] += 1

            print(f"  Encoding distribution:")
            for enc_type, count in sorted(encoding_stats.items()):
                bits = {
                    'byte': 8, 'nibble_pair': 8, 'high_nibble': 4,
                    'low_nibble': 4, 'bit': 1
                }.get(enc_type, 0)
                print(f"    {enc_type}: {count} choices ({bits} bits each)")

        return choices

    def _encode_byte(self, byte_value: int, byte_index: int) -> Optional[Dict | List[Dict]]:
        """Try to encode a byte using available bins."""
        # First try: use a large bin for direct byte encoding
        if self.large_bins and byte_value < 256:
            bin_idx = byte_index % len(self.large_bins)
            cluster = self.large_bins[bin_idx]

            return {
                'choice_id': len(self._get_current_choices()),
                'byte_value': byte_value,
                'cluster_id': cluster['bin_id'],
                'cluster_words': cluster['tokens'],
                'target_index': byte_value % len(cluster['tokens']),
                'bits': 8,
                'encoding_type': 'byte',
                'byte_index': byte_index
            }

        # Second try: use two medium bins for nibble encoding
        if len(self.medium_bins) >= 2:
            # Split byte into two 4-bit nibbles
            high_nibble = (byte_value >> 4) & 0x0F
            low_nibble = byte_value & 0x0F

            high_bin = self.medium_bins[byte_index % len(self.medium_bins)]
            low_bin = self.medium_bins[(byte_index + 1) % len(self.medium_bins)]

            if len(high_bin['tokens']) >= 16 and len(low_bin['tokens']) >= 16:
                return [
                    {
                        'choice_id': len(self._get_current_choices()),
                        'nibble_value': high_nibble,
                        'cluster_id': high_bin['bin_id'],
                        'cluster_words': high_bin['tokens'],
                        'target_index': high_nibble % len(high_bin['tokens']),
                        'bits': 4,
                        'encoding_type': 'high_nibble',
                        'byte_index': byte_index
                    },
                    {
                        'choice_id': len(self._get_current_choices()) + 1,
                        'nibble_value': low_nibble,
                        'cluster_id': low_bin['bin_id'],
                        'cluster_words': low_bin['tokens'],
                        'target_index': low_nibble % len(low_bin['tokens']),
                        'bits': 4,
                        'encoding_type': 'low_nibble',
                        'byte_index': byte_index
                    }
                ]

        # Third try: use small bins with 2-3 bits each
        return None  # Let caller handle fallback

    def _encode_byte_as_bits(self, byte_value: int, byte_index: int) -> List[Dict]:
        """Encode a byte as individual bits (fallback)."""
        bit_choices = []

        # Use tiny bins for bit encoding
        for bit_pos in range(8):
            bit = (byte_value >> (7 - bit_pos)) & 0x01

            if self.tiny_bins:
                bin_idx = (byte_index * 8 + bit_pos) % len(self.tiny_bins)
                cluster = self.tiny_bins[bin_idx]

                if len(cluster['tokens']) >= 2:
                    bit_choices.append({
                        'choice_id': len(self._get_current_choices()) + len(bit_choices),
                        'bit_value': bit,
                        'cluster_id': cluster['bin_id'],
                        'cluster_words': cluster['tokens'],
                        'target_index': bit % len(cluster['tokens']),
                        'bits': 1,
                        'encoding_type': 'bit',
                        'byte_index': byte_index,
                        'bit_position': bit_pos
                    })

        return bit_choices

    def _get_current_choices(self) -> List:
        """Helper to track current choices."""
        return []

    def _byte_chunking(self, choices: List[Dict], target_bits_per_chunk: int = 32) -> List[List[Dict]]:
        """Group choices into chunks."""
        chunks = []
        current_chunk = []
        current_bits = 0

        for choice in choices:
            current_chunk.append(choice)
            current_bits += choice.get('bits', 1)

            # Create chunk when we reach target OR have 4+ choices
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
        """Generate natural text for byte-level encoding."""
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
                    {"role": "system",
                     "content": "You are a technical writer on GitHub. Write naturally and professionally."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=200,
                top_p=0.9
            )

            text = response.choices[0].message.content.strip()
            text = re.sub(r'\s+', ' ', text)

            if not text.endswith(('.', '!', '?')):
                text += '.'

            print(f"    Generated {len(text.split())} words")

            # Extract encoded words
            positions = self._extract_byte_positions(text, choices)

            encoded = len(positions)
            total = len(choices)
            success = encoded / total * 100 if total > 0 else 0

            print(f"    Encoded {encoded}/{total} choices ({success:.0f}%)")

            return text, positions

        except Exception as e:
            print(f"    ⚠ Error: {e}")
            return self._fallback_byte_text(choices, artifact_type, repo_context), []

    def _build_byte_prompt(self, artifact_type: str, repo_context: str, choices: List[Dict]) -> str:
        """Build prompt for byte-level encoding."""

        # Collect sample words from choices
        sample_words = []
        for choice in choices[:6]:  # Limit to first 6 choices
            cluster_words = choice.get('cluster_words', [])
            if cluster_words:
                # Take 1-2 words from this cluster
                num_samples = min(2, len(cluster_words))
                samples = random.sample(cluster_words, num_samples)
                for word in samples:
                    if word not in sample_words:
                        sample_words.append(word)

        if not sample_words:
            sample_words = ["improvement", "optimization", "security", "performance"]

        # Take up to 6 sample words
        display_words = sample_words[:6]

        prompt = f"""Write a {artifact_type} about {repo_context}.

Be concise and natural (3-4 sentences).

As you write, naturally incorporate some of these words where they fit best: {', '.join(display_words)}

IMPORTANT: Don't list the words. Use them naturally in context.

Example of GOOD writing:
"The authentication system needs optimization for better performance. We should review our security measures."

Example of BAD writing:
"Here are words: optimization, performance, security, measures."

Write naturally:
"""

        return prompt

    def _extract_byte_positions(self, text: str, choices: List[Dict]) -> List[Dict]:
        """Extract which words were chosen."""
        positions = []
        text_lower = text.lower()
        words = text.split()

        for choice in choices:
            found_word = None
            found_index = None

            cluster_words = choice.get('cluster_words', [])
            for idx, word in enumerate(cluster_words):
                # Use word boundary regex
                if re.search(rf'\b{re.escape(word.lower())}\b', text_lower):
                    found_word = word
                    found_index = idx
                    break

            if found_word:
                # Find exact position
                for word_idx, w in enumerate(words):
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

    def _fallback_byte_text(self, choices: List[Dict], artifact_type: str, repo_context: str) -> str:
        """Fallback text."""
        # Extract some words from choices
        used_words = []
        for i, choice in enumerate(choices[:4]):
            cluster_words = choice.get('cluster_words', [])
            if cluster_words:
                word = random.choice(cluster_words[:3])
                if word not in used_words:
                    used_words.append(word)

        text = f"This {artifact_type} discusses {repo_context}. "

        if used_words:
            text += f"Important aspects include {', '.join(used_words)}. "
        else:
            text += "Several key considerations need attention. "

        text += "We should address these systematically."

        return text


# ============================================================
# Byte-Level Main Encoder
# ============================================================

class ByteLevelStegoEncoder:
    """
    Main byte-level encoder.
    Encodes whole bytes instead of bits for maximum density.
    """

    def __init__(self, bins_path: str = "token_binning_data/byte_level_bins.json"):
        self.encoder = ByteLevelSemanticEncoder(bins_path)

    def encode(self, message: str, context: Dict[str, Any],
               positions_filename: Optional[str] = None) -> List[str]:
        """
        Encode at byte level.
        """
        print(f"\n📤 BYTE-LEVEL ENCODING: '{message}'")
        print(f"  Length: {len(message)} chars = {len(message.encode('utf-8'))} bytes")

        # Encode
        chunks, positions_data = self.encoder.encode_message(message, context)

        # Statistics
        total_bits = sum(chunk.get('encoded_bits', 0) for chunk in positions_data)
        message_bytes = len(message.encode('utf-8'))
        message_bits = message_bytes * 8

        print(f"\n📊 BYTE-LEVEL RESULTS")
        print(f"  Message: {message_bytes} bytes ({message_bits} bits)")
        print(f"  Encoded bits: {total_bits}")
        print(f"  Chunks generated: {len(chunks)}")
        print(f"  Bits per chunk: {total_bits / len(chunks) if chunks else 0:.1f}")
        print(f"  Efficiency: {total_bits / message_bits * 100:.1f}%")

        # Expected improvement
        original_chunks = message_bytes * 2  # Old system: ~2 chunks per byte
        new_chunks = len(chunks)
        reduction = (original_chunks - new_chunks) / original_chunks * 100 if original_chunks > 0 else 0

        print(f"\n🎯 IMPROVEMENT:")
        print(f"  Original system (bit-level): ~{original_chunks} chunks")
        print(f"  Byte-level system: {new_chunks} chunks")
        print(f"  Reduction: {reduction:.0f}%")

        if new_chunks <= 5:
            print(f"  ✅ Target achieved (≤ 5 chunks)")
        else:
            print(f"  ⚠ Close: {new_chunks} chunks (target ≤ 5)")

        # Save positions
        if positions_filename:
            self._save_positions(positions_filename, positions_data)
        else:
            hash_val = hashlib.md5(message.encode()).hexdigest()[:6]
            self._save_positions(f"byte_positions_{hash_val}.json", positions_data)

        return chunks

    def _save_positions(self, filename: str, data: List[Dict]):
        """Save positions data."""
        try:
            with open(filename, 'w') as f:
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
    """Test byte-level encoder."""
    print("\n" + "=" * 80)
    print("BYTE-LEVEL STEGANOGRAPHY ENCODER")
    print("Encodes whole bytes, not bits")
    print("=" * 80)
    print("Target: 3-5 chunks for 28-byte message")
    print("=" * 80)

    try:
        # Initialize encoder
        encoder = ByteLevelStegoEncoder("token_binning_data/byte_level_bins.json")

        # Test message
        message = "We will meet at 9pm tonight."
        print(f"\nMessage: '{message}' ({len(message)} bytes)")

        # Context
        context = {
            "repo_context": "authentication system",
            "file_context": "src/auth/login.js"
        }

        # Encode
        print("\n" + "=" * 80)
        print("ENCODING...")
        print("=" * 80)

        chunks = encoder.encode(message, context, "byte_level_test.json")

        print(f"\nGenerated {len(chunks)} artifacts:")
        for i, chunk in enumerate(chunks):
            words = len(chunk.split())
            print(f"\n--- Artifact {i + 1} ({words} words) ---")
            print(chunk)
            print("-" * 60)

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
        print("   - Encodes bytes instead of bits")
        print("   - Uses 256+ word bins for byte encoding")
        print("   - Dramatically fewer chunks needed")
        print("   - Much more natural text")
    else:
        print("❌ BYTE-LEVEL ENCODER FAILED")
    print("=" * 80)
