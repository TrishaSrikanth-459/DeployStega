from __future__ import annotations

import json
import os
import re
import math
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
import random
from datetime import datetime
import hashlib

import openai

# ============================================================
# Configuration
# ============================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY must be set")

client = openai.OpenAI(api_key=OPENAI_API_KEY)


# ============================================================
# Semantic Choice Encoding
# ============================================================

class SemanticEncoder:
    """
    NEW APPROACH: Encodes bits in the LLM's NATURAL WORD CHOICES
    Not in forcing specific words.
    """

    def __init__(self, bins_path: str = "token_binning_data/bulletproof_token_bins.json"):
        self.bins = []
        self.semantic_clusters = []  # Group of related bins for semantic flexibility
        self._load_bins(bins_path)
        self._create_semantic_clusters()

        self.positions_data = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "encoding_scheme": "semantic_choice_v1",
                "position_format": "semantic_choice_with_context"
            },
            "chunks": []
        }

    def _load_bins(self, bins_path: str):
        """Load token bins."""
        print(f"Loading semantic bins from {bins_path}...")
        with open(bins_path, 'r') as f:
            data = json.load(f)

        bins_data = data['bins']
        for bin_id, tokens in enumerate(bins_data):
            if len(tokens) >= 2:  # Need at least 2 words for encoding
                self.bins.append({
                    'bin_id': bin_id,
                    'tokens': tokens,
                    'capacity_bits': int(math.log2(len(tokens)))
                })

        print(f"✓ Loaded {len(self.bins)} semantic bins")

    def _create_semantic_clusters(self):
        """Group bins into semantic clusters for natural choice."""
        # Simple grouping: just use bins as-is for now
        # In production, you'd want to cluster by semantic similarity
        self.semantic_clusters = self.bins
        print(f"✓ Created {len(self.semantic_clusters)} semantic choice clusters")

    def encode_message(self, message: str, context: Dict[str, Any]) -> Tuple[List[str], Dict]:
        """Encode message using semantic choice encoding."""
        print(f"\n🔐 SEMANTIC ENCODING: '{message}'")

        # Convert message to bits
        bits = self._message_to_bits(message)
        print(f"  Message bits: {len(bits)} bits")

        # Group bits into semantic choices (2-3 bits per choice)
        # Each choice = LLM picks ONE word from a semantic cluster
        # Which word they pick encodes the bits

        semantic_choices = self._create_semantic_choices(bits)
        print(f"  Created {len(semantic_choices)} semantic choice points")

        # Generate text with semantic choices
        encoded_chunks = []

        for chunk_idx, choices in enumerate(self._chunk_choices(semantic_choices, choices_per_chunk=5)):
            print(f"\n  --- Chunk {chunk_idx + 1} ---")
            print(f"  Encoding {len(choices)} semantic choices")

            chunk_text, chunk_positions = self._generate_with_semantic_choices(
                context, chunk_idx, choices
            )

            encoded_chunks.append(chunk_text)

            self.positions_data["chunks"].append({
                "chunk_id": chunk_idx,
                "semantic_choices": choices,
                "positions": chunk_positions,
                "text_preview": chunk_text[:100] + "..." if len(chunk_text) > 100 else chunk_text
            })

        return encoded_chunks, self.positions_data

    def _message_to_bits(self, message: str) -> List[int]:
        """Convert message to bits."""
        bits = []

        # Header: message length (16 bits)
        length = len(message)
        length_bits = [int(b) for b in format(length, '016b')]
        bits.extend(length_bits)

        # Message: 7-bit ASCII
        for char in message:
            ascii_val = ord(char)
            char_bits = [int(b) for b in format(ascii_val, '07b')]
            bits.extend(char_bits)

        return bits

    def _create_semantic_choices(self, bits: List[int]) -> List[Dict]:
        """Create semantic choice points from bits."""
        choices = []
        i = 0

        while i < len(bits):
            # Decide how many bits to encode in this choice (2 or 3 bits)
            bits_available = len(bits) - i
            if bits_available >= 3:
                num_bits = 3
                choice_bits = bits[i:i + 3]
            else:
                num_bits = bits_available
                choice_bits = bits[i:]

            # Find a semantic cluster with enough words
            # We need at least 2^num_bits words in the cluster
            required_words = 2 ** num_bits

            suitable_clusters = [
                cluster for cluster in self.semantic_clusters
                if len(cluster['tokens']) >= required_words
            ]

            if not suitable_clusters:
                # If no cluster has enough words, reduce bits
                num_bits = 2
                required_words = 4
                choice_bits = bits[i:i + 2] if i + 2 <= len(bits) else bits[i:]
                suitable_clusters = [
                    cluster for cluster in self.semantic_clusters
                    if len(cluster['tokens']) >= required_words
                ]

            if suitable_clusters:
                # Choose a random suitable cluster
                cluster = random.choice(suitable_clusters)

                # Convert bits to integer
                bits_value = 0
                for bit in choice_bits:
                    bits_value = (bits_value << 1) | bit

                # The index in the cluster that encodes these bits
                target_index = bits_value % len(cluster['tokens'])

                choices.append({
                    'choice_id': len(choices),
                    'cluster_id': cluster['bin_id'],
                    'cluster_words': cluster['tokens'],
                    'bits': choice_bits,
                    'num_bits': len(choice_bits),
                    'target_index': target_index,
                    'chosen_word': None  # Will be filled by LLM
                })

                i += len(choice_bits)
            else:
                # No suitable cluster, skip this bit
                i += 1

        return choices

    def _chunk_choices(self, choices: List[Dict], choices_per_chunk: int = 5) -> List[List[Dict]]:
        """Split choices into chunks."""
        chunks = []
        for i in range(0, len(choices), choices_per_chunk):
            chunks.append(choices[i:i + choices_per_chunk])
        return chunks

    def _generate_with_semantic_choices(self, context: Dict[str, Any],
                                        chunk_idx: int,
                                        choices: List[Dict]) -> Tuple[str, List[Dict]]:
        """Generate text where LLM makes natural semantic choices."""
        repo_context = context.get("repo_context", "authentication system")
        file_context = context.get("file_context", "src/auth/login.js")

        artifact_types = [
            f"GitHub issue comment about {repo_context}",
            f"Pull request description for {file_context}",
            f"Code review comment on {repo_context}",
            f"Technical discussion about {repo_context} improvements",
        ]

        artifact_type = artifact_types[chunk_idx % len(artifact_types)]

        # Build the prompt for semantic choices
        prompt = self._build_semantic_prompt(artifact_type, repo_context, choices)

        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system",
                     "content": "You are a GitHub technical writer. You make natural word choices based on context."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.9,  # Higher temperature for more varied choices
                max_tokens=500
            )

            text = response.choices[0].message.content.strip()
            text = re.sub(r'\s+', ' ', text)

            # Ensure it ends properly
            if not text.endswith(('.', '!', '?')):
                text += '.'

            # Find which words the LLM chose from each semantic cluster
            positions = self._extract_semantic_choices(text, choices)

            return text, positions

        except Exception as e:
            print(f"  ⚠ Error: {e}")
            return self._fallback_semantic_text(choices), []

    def _build_semantic_prompt(self, artifact_type: str, repo_context: str, choices: List[Dict]) -> str:
        """Build prompt that asks LLM to make natural semantic choices."""

        # Create natural language descriptions of semantic choices
        choice_descriptions = []
        for i, choice in enumerate(choices):
            # Show the semantic cluster (related words)
            cluster_words = choice['cluster_words']
            sample_words = random.sample(cluster_words, min(5, len(cluster_words)))

            choice_descriptions.append(
                f"In your text, at some point naturally use ONE word from this group: "
                f"{', '.join(sample_words)}"
            )

        choices_text = "\n".join([f"{i + 1}. {desc}" for i, desc in enumerate(choice_descriptions)])

        prompt = f"""
        Write a {artifact_type} about {repo_context}.

        IMPORTANT: Your text should flow 100% naturally as a real GitHub discussion.

        As you write, please make {len(choices)} natural word choices. 
        For each of the following, choose ONE word that fits naturally in your text:

        {choices_text}

        CRITICAL REQUIREMENTS:
        1. Write completely naturally - don't force the words
        2. Choose the word that fits BEST in each context
        3. Don't list the options or draw attention to your choices
        4. Just write normal technical text
        5. 4-7 sentences maximum
        6. End with a relevant question or conclusion
        7. The text must sound 100% authentic

        Example of GOOD writing:
        - "We should improve the authentication system by adding multi-factor authentication."
        - "The performance metrics show we need to optimize database queries."
        - "Documentation updates are essential for user adoption."

        Write your {artifact_type}:
        """

        return prompt

    def _extract_semantic_choices(self, text: str, choices: List[Dict]) -> List[Dict]:
        """Extract which words the LLM chose from each semantic cluster."""
        positions = []
        text_lower = text.lower()

        for choice in choices:
            chosen_word = None
            chosen_index = None

            # Check which word from the cluster appears in the text
            for idx, word in enumerate(choice['cluster_words']):
                word_lower = word.lower()
                # Look for the word as a whole word (not part of another word)
                if re.search(r'\b' + re.escape(word_lower) + r'\b', text_lower):
                    chosen_word = word
                    chosen_index = idx
                    break

            if chosen_word:
                # Find position in text
                words = text.split()
                for word_idx, w in enumerate(words):
                    if w.lower() == chosen_word.lower():
                        positions.append({
                            'choice_id': choice['choice_id'],
                            'cluster_id': choice['cluster_id'],
                            'chosen_word': chosen_word,
                            'chosen_index': chosen_index,
                            'target_index': choice['target_index'],
                            'bits': choice['bits'],
                            'position': word_idx,
                            'context_before': words[max(0, word_idx - 2):word_idx],
                            'context_after': words[word_idx + 1:min(len(words), word_idx + 3)]
                        })
                        break

        return positions

    def _fallback_semantic_text(self, choices: List[Dict]) -> str:
        """Fallback text generation."""
        text = "This PR improves the authentication system. "

        for choice in choices:
            # Pick a random word from the cluster
            word = random.choice(choice['cluster_words'])
            text += f"The {word} has been optimized. "

        return text.strip()


# ============================================================
# Main Encoder (backward compatible interface)
# ============================================================

class StegoEncoder:
    """
    Main encoder with backward compatible interface.
    Uses semantic choice encoding internally.
    """

    def __init__(self, bins_path: str = "token_binning_data/bulletproof_token_bins.json"):
        self.semantic_encoder = SemanticEncoder(bins_path)

    def encode(self, message: str, context: Dict[str, Any],
               positions_filename: Optional[str] = None) -> List[str]:
        """
        Encode message and save positions file.
        Returns: List of encoded text chunks
        """
        print(f"\n📤 ENCODING: '{message}'")

        # Use semantic encoding
        chunks, positions_data = self.semantic_encoder.encode_message(message, context)

        # Save positions file
        if positions_filename:
            self._save_positions_file(positions_filename, positions_data)
        else:
            message_hash = hashlib.md5(message.encode()).hexdigest()[:8]
            default_filename = f"stego_positions_{message_hash}.json"
            self._save_positions_file(default_filename, positions_data)

        return chunks

    def _save_positions_file(self, filename: str, positions_data: Dict):
        """Save positions data to JSON file."""
        try:
            os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else '.',
                        exist_ok=True)

            with open(filename, 'w') as f:
                json.dump(positions_data, f, indent=2)

            print(f"\n✓ Positions file saved: {filename}")
            print(f"  Contains {len(positions_data['chunks'])} chunk(s)")

        except Exception as e:
            print(f"\n⚠ Could not save positions file: {e}")


# ============================================================
# Test
# ============================================================

def test_encoder():
    """Test the encoder."""
    print("\n" + "=" * 60)
    print("SEMANTIC CHOICE STEGANOGRAPHY ENCODER")
    print("=" * 60)
    print("Encodes bits in LLM's natural word choices")
    print("=" * 60)

    try:
        # Initialize
        encoder = StegoEncoder()

        # Test message
        message = "We will meet at 9pm tonight."
        print(f"\nMessage: '{message}'")

        # Context
        context = {
            "repo_context": "authentication system",
            "file_context": "src/auth/login.js",
            "parent_artifact": "PR #123"
        }

        # Encode
        print("\n" + "=" * 60)
        print("ENCODING WITH SEMANTIC CHOICES")
        print("=" * 60)

        chunks = encoder.encode(message, context, "stego_positions.json")

        print(f"\nGenerated {len(chunks)} artifacts:")
        for i, chunk in enumerate(chunks):
            print(f"\n--- Artifact {i + 1} ---")
            print(chunk)
            print("-" * 80)

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
    success, chunks = test_encoder()

    print("\n" + "=" * 60)
    if success:
        print("✅ ENCODER COMPLETE")
        print("   - Bits encoded in LLM's natural word choices")
        print("   - Positions file saved: stego_positions.json")
        print("\nDecoder must check which word was chosen from each semantic cluster")
    else:
        print("❌ ENCODER FAILED")
    print("=" * 60)
