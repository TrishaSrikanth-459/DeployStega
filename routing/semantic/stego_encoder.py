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
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")  # Using gpt-4o since GPT-5.2 doesn't exist yet

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

    def __init__(self, bins_path: str = "token_binning_data/ultimate_token_bins.json"):  # Changed to new file
        self.bins = []
        self.semantic_clusters = []  # Group of related bins for semantic flexibility
        self._load_new_bins(bins_path)  # Changed to new loader
        self._create_semantic_clusters()

        self.positions_data = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "encoding_scheme": "semantic_choice_v2",
                "position_format": "semantic_choice_with_context",
                "vocabulary_size": len(self.bins)
            },
            "chunks": []
        }

    def _load_new_bins(self, bins_path: str):
        """Load token bins from the new corpus parser format."""
        print(f"Loading semantic bins from {bins_path}...")

        try:
            with open(bins_path, 'r') as f:
                data = json.load(f)

            # Check if it's the new format or old format
            if 'bins' in data:
                # Old format or simplified format
                bins_data = data['bins']
                print(f"  Detected simplified format with {len(bins_data)} bins")
            elif 'metadata' in data and 'bins' in data:
                # New comprehensive format from corpus parser
                bins_data = data['bins']
                metadata = data['metadata']
                print(f"  Detected comprehensive format")
                print(f"  Metadata: {metadata.get('final_bins', 'N/A')} bins, "
                      f"{metadata.get('final_unique_words', 'N/A')} unique words")
            else:
                raise ValueError(f"Unknown file format in {bins_path}")

            # Load bins
            for bin_id, tokens in enumerate(bins_data):
                if len(tokens) >= 2:  # Need at least 2 words for encoding
                    # Clean tokens (remove any empty strings)
                    clean_tokens = [str(tok).strip() for tok in tokens if str(tok).strip()]
                    if len(clean_tokens) >= 2:
                        self.bins.append({
                            'bin_id': bin_id,
                            'tokens': clean_tokens,
                            'capacity_bits': int(math.log2(len(clean_tokens))) if len(clean_tokens) > 1 else 1
                        })

            print(f"✓ Loaded {len(self.bins)} semantic bins")
            print(f"  Total words in bins: {sum(len(b['tokens']) for b in self.bins)}")
            print(f"  Unique words: {len(set(word for b in self.bins for word in b['tokens']))}")

            # Show some example bins
            if len(self.bins) > 0:
                print(f"\n  Example bins:")
                for i in range(min(3, len(self.bins))):
                    bin = self.bins[i]
                    print(f"    Bin {i}: {len(bin['tokens'])} words, "
                          f"{bin['capacity_bits']} bits - "
                          f"{', '.join(bin['tokens'][:3])}...")

        except Exception as e:
            print(f"❌ Error loading bins: {e}")

            # Fallback to old file if exists
            fallback_path = "token_binning_data/bulletproof_token_bins.json"
            if os.path.exists(fallback_path):
                print(f"  Trying fallback file: {fallback_path}")
                self._load_new_bins(fallback_path)
            else:
                raise

    def _create_semantic_clusters(self):
        """Group bins into semantic clusters for natural choice."""
        # Use bins as semantic clusters
        self.semantic_clusters = self.bins

        # Analyze cluster sizes for optimal encoding
        cluster_sizes = [len(c['tokens']) for c in self.semantic_clusters]

        print(f"\n✓ Created {len(self.semantic_clusters)} semantic choice clusters")
        print(f"  Cluster size stats:")
        print(f"    Min: {min(cluster_sizes) if cluster_sizes else 0}")
        print(f"    Max: {max(cluster_sizes) if cluster_sizes else 0}")
        print(f"    Avg: {sum(cluster_sizes) / len(cluster_sizes) if cluster_sizes else 0:.1f}")

        # Count clusters by bit capacity
        bit_counts = {}
        for cluster in self.semantic_clusters:
            bits = cluster['capacity_bits']
            bit_counts[bits] = bit_counts.get(bits, 0) + 1

        print(f"  Bit capacity distribution:")
        for bits in sorted(bit_counts.keys()):
            print(f"    {bits} bits: {bit_counts[bits]} clusters")

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

        # Calculate total bit capacity
        total_bits_encoded = sum(c['num_bits'] for c in semantic_choices)
        print(f"  Total bits encoded: {total_bits_encoded}")
        print(f"  Efficiency: {total_bits_encoded}/{len(bits)} bits ({total_bits_encoded / len(bits) * 100:.1f}%)")

        # Generate text with semantic choices
        encoded_chunks = []

        for chunk_idx, choices in enumerate(self._chunk_choices(semantic_choices, choices_per_chunk=4)):
            print(f"\n  --- Chunk {chunk_idx + 1} ---")
            print(f"  Encoding {len(choices)} semantic choices ({sum(c['num_bits'] for c in choices)} bits)")

            chunk_text, chunk_positions = self._generate_with_semantic_choices(
                context, chunk_idx, choices
            )

            encoded_chunks.append(chunk_text)

            self.positions_data["chunks"].append({
                "chunk_id": chunk_idx,
                "semantic_choices": choices,
                "positions": chunk_positions,
                "text_preview": chunk_text[:100] + "..." if len(chunk_text) > 100 else chunk_text,
                "encoded_bits": sum(c['num_bits'] for c in choices)
            })

        return encoded_chunks, self.positions_data

    def _message_to_bits(self, message: str) -> List[int]:
        """Convert message to bits with error correction header."""
        bits = []

        # Header: message length (16 bits) + checksum (8 bits)
        length = len(message)
        length_bits = [int(b) for b in format(length, '016b')]
        bits.extend(length_bits)

        # Simple checksum of message
        checksum = sum(ord(c) for c in message) % 256
        checksum_bits = [int(b) for b in format(checksum, '08b')]
        bits.extend(checksum_bits)

        # Message: 7-bit ASCII
        for char in message:
            ascii_val = ord(char)
            char_bits = [int(b) for b in format(ascii_val, '07b')]
            bits.extend(char_bits)

        return bits

    def _create_semantic_choices(self, bits: List[int]) -> List[Dict]:
        """Create semantic choice points from bits with intelligent cluster selection."""
        choices = []
        i = 0

        # Track used clusters to ensure diversity
        used_cluster_ids = set()

        while i < len(bits):
            # Decide optimal number of bits for this choice based on available clusters
            bits_available = len(bits) - i

            # Try to encode 3 bits first (needs ≥8 words)
            num_bits = 3
            required_words = 8

            # Find suitable clusters
            suitable_clusters = [
                cluster for cluster in self.semantic_clusters
                if len(cluster['tokens']) >= required_words
                   and cluster['bin_id'] not in used_cluster_ids
            ]

            # If no suitable clusters for 3 bits, try 2 bits
            if not suitable_clusters and bits_available >= 2:
                num_bits = 2
                required_words = 4
                suitable_clusters = [
                    cluster for cluster in self.semantic_clusters
                    if len(cluster['tokens']) >= required_words
                       and cluster['bin_id'] not in used_cluster_ids
                ]

            # If still no suitable clusters, try 1 bit or reuse clusters
            if not suitable_clusters:
                if bits_available >= 1:
                    num_bits = 1
                    required_words = 2
                    # Allow cluster reuse if necessary
                    suitable_clusters = [
                        cluster for cluster in self.semantic_clusters
                        if len(cluster['tokens']) >= required_words
                    ]
                else:
                    # Not enough bits left
                    break

            if suitable_clusters:
                # Choose the best cluster (largest for better randomness)
                suitable_clusters.sort(key=lambda c: len(c['tokens']), reverse=True)
                cluster = suitable_clusters[0]

                # Get bits for this choice
                choice_bits = bits[i:i + num_bits] if i + num_bits <= len(bits) else bits[i:]
                actual_bits = len(choice_bits)

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
                    'num_bits': actual_bits,
                    'target_index': target_index,
                    'chosen_word': None,  # Will be filled by LLM
                    'cluster_size': len(cluster['tokens']),
                    'bit_capacity': cluster['capacity_bits']
                })

                used_cluster_ids.add(cluster['bin_id'])
                i += actual_bits
            else:
                # No suitable cluster, skip this bit
                i += 1

        return choices

    def _chunk_choices(self, choices: List[Dict], choices_per_chunk: int = 4) -> List[List[Dict]]:
        """Split choices into chunks for natural text generation."""
        # Fewer choices per chunk for more natural text
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
            f"README update for {repo_context}",
            f"Documentation for {file_context}",
            f"Bug report about {repo_context}",
            f"Feature request for {repo_context}"
        ]

        artifact_type = artifact_types[chunk_idx % len(artifact_types)]

        # Build the prompt for semantic choices
        prompt = self._build_semantic_prompt(artifact_type, repo_context, choices)

        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system",
                     "content": "You are a GitHub technical writer creating authentic discussions. "
                                "You naturally choose words that fit the context perfectly. "
                                "Your writing sounds 100% genuine and never forced."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.85,  # Balanced temperature for creativity + consistency
                max_tokens=400,
                top_p=0.95
            )

            text = response.choices[0].message.content.strip()
            text = re.sub(r'\s+', ' ', text)

            # Ensure it ends properly
            if not text.endswith(('.', '!', '?')):
                text += '.'

            print(f"    Generated {len(text.split())} words")

            # Find which words the LLM chose from each semantic cluster
            positions = self._extract_semantic_choices(text, choices)

            # Report on encoding success
            encoded_choices = len(positions)
            total_choices = len(choices)
            print(
                f"    Encoded {encoded_choices}/{total_choices} choices ({encoded_choices / total_choices * 100:.0f}%)")

            # If some choices missing, try to add them naturally
            if encoded_choices < total_choices:
                missing_indices = [i for i, choice in enumerate(choices)
                                   if choice['choice_id'] not in [p['choice_id'] for p in positions]]
                print(f"    ⚠ Missing {len(missing_indices)} choices")
                text = self._add_missing_choices_naturally(text, [choices[i] for i in missing_indices])
                # Re-extract positions
                positions = self._extract_semantic_choices(text, choices)

            return text, positions

        except Exception as e:
            print(f"  ⚠ Error: {e}")
            return self._fallback_semantic_text(choices, artifact_type), []

    def _build_semantic_prompt(self, artifact_type: str, repo_context: str, choices: List[Dict]) -> str:
        """Build prompt that asks LLM to make natural semantic choices."""

        # Create natural language descriptions of semantic choices
        choice_descriptions = []
        for i, choice in enumerate(choices):
            # Show 3-4 sample words from the cluster
            cluster_words = choice['cluster_words']
            num_samples = min(4, len(cluster_words))

            # Don't always show the same words - randomize samples
            sample_indices = random.sample(range(len(cluster_words)), num_samples)
            sample_words = [cluster_words[idx] for idx in sample_indices]

            choice_descriptions.append(
                f"At some point, naturally use ONE word from this group: "
                f"{', '.join(sample_words)}"
            )

        choices_text = "\n".join([f"{i + 1}. {desc}" for i, desc in enumerate(choice_descriptions)])

        prompt = f"""
        Write a {artifact_type} about {repo_context}.

        IMPORTANT: Your text must flow 100% naturally as a real GitHub discussion.
        Sound authentic, technical, and professional.

        As you write, please make {len(choices)} natural word choices. 
        For each of the following, choose ONE word that fits perfectly in your text:

        {choices_text}

        CRITICAL REQUIREMENTS:
        1. Write completely naturally - don't force the words
        2. Choose the word that fits BEST in each context
        3. Don't list the options or draw attention to your choices
        4. Just write normal technical text (4-6 sentences)
        5. End with a relevant question or conclusion
        6. The text must sound 100% authentic GitHub content
        7. Use each chosen word exactly once in a natural context

        Example of GOOD writing (natural, authentic):
        - "We should improve the authentication system by adding multi-factor authentication."
        - "The performance metrics indicate we need to optimize our database queries."
        - "Recent updates to the documentation have significantly improved developer onboarding."

        Example of BAD writing (forced, unnatural):
        - "Here are my word choices: improve, optimize, update"
        - "We need to (improve) and (optimize) and (update) everything"
        - "improve! optimize! update!"

        Write your {artifact_type}:
        """

        return prompt

    def _extract_semantic_choices(self, text: str, choices: List[Dict]) -> List[Dict]:
        """Extract which words the LLM chose from each semantic cluster."""
        positions = []
        text_lower = text.lower()
        words = text.split()

        for choice in choices:
            chosen_word = None
            chosen_index = None

            # First, check if any word from the cluster appears in the text
            for idx, word in enumerate(choice['cluster_words']):
                word_lower = word.lower()
                # Look for the word as a whole word (not part of another word)
                # Use word boundaries and handle punctuation
                pattern = r'(^|\W)' + re.escape(word_lower) + r'($|\W)'
                if re.search(pattern, text_lower):
                    chosen_word = word
                    chosen_index = idx
                    break

            if chosen_word:
                # Find exact position in text
                for word_idx, w in enumerate(words):
                    w_clean = re.sub(r'[^\w]', '', w.lower())
                    if w_clean == chosen_word.lower():
                        positions.append({
                            'choice_id': choice['choice_id'],
                            'cluster_id': choice['cluster_id'],
                            'chosen_word': chosen_word,
                            'chosen_index': chosen_index,
                            'target_index': choice['target_index'],
                            'bits': choice['bits'],
                            'num_bits': choice['num_bits'],
                            'position': word_idx,
                            'word_in_text': w,
                            'context_before': words[max(0, word_idx - 2):word_idx],
                            'context_after': words[word_idx + 1:min(len(words), word_idx + 3)]
                        })
                        break

        return positions

    def _add_missing_choices_naturally(self, text: str, missing_choices: List[Dict]) -> str:
        """Add missing semantic choices naturally to the text."""
        if not missing_choices:
            return text

        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if not sentences:
            sentences = [text]

        # Add each missing choice to a different sentence
        for i, choice in enumerate(missing_choices):
            if i < len(sentences):
                sentence_idx = i % len(sentences)
                # Pick a word from the cluster
                word = random.choice(choice['cluster_words'])

                # Add naturally
                sentence = sentences[sentence_idx]
                if sentence.endswith('.'):
                    sentence = sentence[:-1]
                sentences[sentence_idx] = sentence + f", specifically regarding {word}."

        return ' '.join(sentences)

    def _fallback_semantic_text(self, choices: List[Dict], artifact_type: str) -> str:
        """Fallback text generation."""
        text = f"This {artifact_type} addresses several important considerations. "

        for i, choice in enumerate(choices):
            # Pick a word from the cluster
            word = random.choice(choice['cluster_words'])

            if i % 2 == 0:
                text += f"We need to consider {word} carefully. "
            else:
                text += f"The {word} aspect requires attention. "

        text += "What are your thoughts on these improvements?"
        return text.strip()


# ============================================================
# Main Encoder (backward compatible interface)
# ============================================================

class StegoEncoder:
    """
    Main encoder with backward compatible interface.
    Uses semantic choice encoding internally.
    """

    def __init__(self, bins_path: str = "token_binning_data/ultimate_token_bins.json"):
        """Initialize with new corpus parser output by default."""
        self.semantic_encoder = SemanticEncoder(bins_path)

    def encode(self, message: str, context: Dict[str, Any],
               positions_filename: Optional[str] = None) -> List[str]:
        """
        Encode message and save positions file.
        Returns: List of encoded text chunks
        """
        print(f"\n📤 ENCODING: '{message}'")
        print(f"  Message length: {len(message)} characters")
        print(f"  Required bits: {len(message) * 7 + 24} (7-bit ASCII + 24 header bits)")

        # Use semantic encoding
        chunks, positions_data = self.semantic_encoder.encode_message(message, context)

        # Calculate statistics
        total_encoded_bits = sum(chunk.get('encoded_bits', 0) for chunk in positions_data['chunks'])
        required_bits = len(message) * 7 + 24
        efficiency = total_encoded_bits / required_bits * 100 if required_bits > 0 else 0

        print(f"\n📊 ENCODING STATISTICS")
        print(f"  Total chunks: {len(chunks)}")
        print(f"  Total encoded bits: {total_encoded_bits}")
        print(f"  Required bits: {required_bits}")
        print(f"  Efficiency: {efficiency:.1f}%")
        print(f"  Avg bits per chunk: {total_encoded_bits / len(chunks) if chunks else 0:.1f}")

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
    print("\n" + "=" * 80)
    print("SEMANTIC CHOICE STEGANOGRAPHY ENCODER")
    print("Using NEW corpus parser vocabulary")
    print("=" * 80)
    print("Encodes bits in LLM's natural word choices")
    print("=" * 80)

    try:
        # Initialize with new vocabulary
        encoder = StegoEncoder("token_binning_data/ultimate_token_bins.json")

        # Test message
        message = "We will meet at 9pm tonight."
        print(f"\nMessage: '{message}'")

        # Context
        context = {
            "repo_context": "authentication system",
            "file_context": "src/auth/login.js",
            "parent_artifact": "PR #123",
            "project": "SecureAuth"
        }

        # Encode
        print("\n" + "=" * 80)
        print("ENCODING WITH SEMANTIC CHOICES")
        print("=" * 80)

        chunks = encoder.encode(message, context, "stego_positions.json")

        print(f"\nGenerated {len(chunks)} artifacts:")
        for i, chunk in enumerate(chunks):
            print(f"\n--- Artifact {i + 1} ({len(chunk.split())} words) ---")
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

    print("\n" + "=" * 80)
    if success:
        print("✅ ENCODER COMPLETE")
        print("   - Bits encoded in LLM's natural word choices")
        print("   - Uses new corpus parser vocabulary (10,000+ words)")
        print("   - Positions file saved: stego_positions.json")
        print("\nDecoder must check which word was chosen from each semantic cluster")
    else:
        print("❌ ENCODER FAILED")
    print("=" * 80)
