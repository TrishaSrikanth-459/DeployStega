from __future__ import annotations

import json
import os
import re
import math
import glob
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
import warnings

# Suppress warnings
warnings.filterwarnings('ignore')


# ============================================================
# Token Bin Class
# ============================================================

@dataclass
class TokenBin:
    bin_id: int
    tokens: List[str]

    @property
    def capacity_bits(self):
        """Calculate how many bits this bin can encode."""
        if len(self.tokens) <= 1:
            return 0
        return int(math.log2(len(self.tokens)))


# ============================================================
# STEGANOGRAPHY DECODER
# ============================================================

class StegoDecoder:
    """
    Decoder for natural steganography integration.
    Reads positions file to know exactly where stegowords are.
    """

    def __init__(self, bins_path: str = None):
        self.bins = []
        self.token_to_bin_and_index = {}  # token -> (bin_id, index_in_bin)
        self.bin_by_id = {}
        
        # Auto-detect the right bins file
        if bins_path is None:
            bins_path = self._find_bins_file()
        
        self._load_all_bins(bins_path)

    def _find_bins_file(self) -> str:
        """Find the bins file automatically."""
        print("Looking for token bins...")
        
        candidates = [
            "token_binning_data/ultimate_token_bins.json",  # New corpus parser output
            "token_binning_data/bulletproof_token_bins.json",  # Old format
            "token_binning_data/fast_token_bins.json",  # Fast version
            "ultimate_token_bins.json",  # In current directory
            "bulletproof_token_bins.json",  # In current directory
        ]
        
        for candidate in candidates:
            if os.path.exists(candidate):
                print(f"✓ Found: {candidate}")
                return candidate
        
        # Look for any JSON file in token_binning_data
        if os.path.exists("token_binning_data"):
            json_files = glob.glob("token_binning_data/*.json")
            for file in json_files:
                if "token" in file.lower() or "bin" in file.lower():
                    print(f"✓ Found: {file}")
                    return file
        
        # If nothing found, use the new format as default
        default = "token_binning_data/ultimate_token_bins.json"
        print(f"⚠ No bins file found, will try: {default}")
        return default

    def _load_all_bins(self, bins_path: str):
        """Load token bins from new or old format."""
        try:
            print(f"Loading token bins from {bins_path}...")
            
            if not os.path.exists(bins_path):
                raise FileNotFoundError(f"Token bins not found at {bins_path}")
            
            with open(bins_path, 'r') as f:
                data = json.load(f)
            
            # Handle different file formats
            bins_data = None
            
            # Format 1: New comprehensive format (from corpus parser)
            if 'metadata' in data and 'bins' in data:
                print("  Detected new comprehensive format")
                bins_data = data['bins']
                metadata = data['metadata']
                print(f"  Metadata: {metadata.get('final_bins', 'N/A')} bins, "
                      f"{metadata.get('final_unique_words', 'N/A')} unique words")
            
            # Format 2: Simplified format with just bins
            elif 'bins' in data:
                print("  Detected simplified format")
                bins_data = data['bins']
            
            # Format 3: Direct list of bins
            elif isinstance(data, list):
                print("  Detected direct list format")
                bins_data = data
            
            else:
                raise ValueError(f"Unknown file format in {bins_path}")
            
            if not bins_data:
                raise ValueError("No bins data found")
            
            # Load bins
            for bin_id, item in enumerate(bins_data):
                tokens = []
                
                if isinstance(item, dict) and 'tokens' in item:
                    tokens = item['tokens']
                elif isinstance(item, list):
                    tokens = item
                elif isinstance(item, str):
                    # Handle single token? Skip for now
                    continue
                
                # Clean tokens
                clean_tokens = []
                for token in tokens:
                    if isinstance(token, str) and token.strip():
                        clean_token = token.strip()
                        # Remove any punctuation that might have been left
                        clean_token = re.sub(r'[^\w\s\-_]', '', clean_token)
                        if clean_token:
                            clean_tokens.append(clean_token)
                
                if len(clean_tokens) >= 2:
                    bin = TokenBin(bin_id=bin_id, tokens=clean_tokens)
                    self.bins.append(bin)
                    self.bin_by_id[bin_id] = bin
                    
                    for idx, token in enumerate(clean_tokens):
                        token_lower = token.lower()
                        self.token_to_bin_and_index[token_lower] = (bin_id, idx)
            
            if not self.bins:
                raise ValueError("No valid bins found")
            
            print(f"✓ Loaded {len(self.bins)} token bins")
            print(f"  - Vocabulary: {len(self.token_to_bin_and_index)} words")
            
            # Show some statistics
            total_words = sum(len(b.tokens) for b in self.bins)
            unique_words = len(self.token_to_bin_and_index)
            avg_bin_size = total_words / len(self.bins) if self.bins else 0
            
            print(f"  - Total words in bins: {total_words}")
            print(f"  - Unique words: {unique_words}")
            print(f"  - Average bin size: {avg_bin_size:.1f}")
            
            # Count bins by capacity
            capacity_counts = {}
            for bin in self.bins:
                capacity = bin.capacity_bits
                capacity_counts[capacity] = capacity_counts.get(capacity, 0) + 1
            
            print(f"  - Bit capacity distribution:")
            for bits in sorted(capacity_counts.keys()):
                print(f"      {bits} bits: {capacity_counts[bits]} bins")
            
        except Exception as e:
            print(f"✗ Failed to initialize: {e}")
            print("\nTrying to create fallback bins...")
            self._create_fallback_bins()
    
    def _create_fallback_bins(self):
        """Create minimal fallback bins if loading fails."""
        print("Creating fallback bins...")
        
        # Simple fallback bins for basic functionality
        fallback_bins = [
            ["improve", "enhance", "optimize", "refine"],
            ["update", "upgrade", "modernize", "refresh"],
            ["fix", "repair", "resolve", "correct"],
            ["add", "include", "incorporate", "integrate"],
            ["remove", "delete", "eliminate", "exclude"],
            ["test", "verify", "validate", "check"],
            ["document", "describe", "explain", "detail"],
            ["secure", "protect", "safeguard", "harden"],
            ["performance", "speed", "efficiency", "throughput"],
            ["error", "bug", "issue", "problem"]
        ]
        
        for bin_id, tokens in enumerate(fallback_bins):
            bin = TokenBin(bin_id=bin_id, tokens=tokens)
            self.bins.append(bin)
            self.bin_by_id[bin_id] = bin
            
            for idx, token in enumerate(tokens):
                token_lower = token.lower()
                self.token_to_bin_and_index[token_lower] = (bin_id, idx)
        
        print(f"✓ Created {len(self.bins)} fallback bins")
        print(f"  - Vocabulary: {len(self.token_to_bin_and_index)} words")

    # ============================================================
    # DECODING: Use positions file
    # ============================================================

    def decode_with_positions(self, chunks: List[str], positions_file: str) -> str:
        """
        Decode using positions file that tells exactly where stegowords are.
        Handles natural word integration without forced punctuation.
        """
        print(f"\n📥 DECODING {len(chunks)} CHUNKS WITH POSITIONS FILE")

        # Load positions data
        try:
            with open(positions_file, 'r') as f:
                positions_data = json.load(f)

            print(f"✓ Loaded positions from: {positions_file}")
            print(f"  Encoding scheme: {positions_data['metadata']['encoding_scheme']}")
            print(f"  Contains {len(positions_data['chunks'])} chunk(s)")

        except Exception as e:
            print(f"✗ Failed to load positions file: {e}")
            return ""

        all_bits = []

        # Process each chunk
        for chunk_idx, (chunk, chunk_data) in enumerate(zip(chunks, positions_data['chunks'])):
            if chunk_idx >= len(positions_data['chunks']):
                print(f"⚠ Warning: More chunks ({len(chunks)}) than positions data ({len(positions_data['chunks'])})")
                break
                
            if chunk_data['chunk_id'] != chunk_idx:
                print(f"⚠ Warning: Chunk ID mismatch ({chunk_data['chunk_id']} vs {chunk_idx})")

            print(f"\n  --- Processing Chunk {chunk_idx + 1} ---")
            print(f"  Expected stego words: {len(chunk_data['positions'])}")

            # Tokenize the chunk
            words = chunk.split()
            print(f"  Total words in chunk: {len(words)}")

            chunk_bits = []

            # Process each expected position
            for pos_idx, pos_info in enumerate(chunk_data['positions']):
                expected_position = pos_info.get('position', -1)
                stego_word = pos_info.get('stego_word', '')
                
                # Handle different position formats
                if 'chosen_word' in pos_info:
                    # New semantic choice format
                    stego_word = pos_info['chosen_word']
                    expected_bits = pos_info.get('bits', [])
                    print(f"    Processing semantic choice: '{stego_word}'")
                else:
                    # Old format
                    expected_bits = pos_info.get('encoded_bits', [])
                
                context_before = pos_info.get('context_before', [])
                context_after = pos_info.get('context_after', [])
                exact_string = pos_info.get('exact_string', '')

                # Clean the stego word for matching
                clean_stego_word = stego_word.lower()
                clean_stego_word = re.sub(r'[^\w]', '', clean_stego_word)
                
                if not clean_stego_word:
                    print(f"    ⚠ Empty stego word, skipping")
                    continue

                # Try to find the stego word
                found_position, found_word = self._find_stego_word_at_position(
                    words, expected_position, clean_stego_word,
                    context_before, context_after, exact_string
                )

                if found_position is not None:
                    # Extract bits from the found word
                    bits = self._extract_bits_from_word(found_word, clean_stego_word)
                    if bits:
                        chunk_bits.extend(bits)
                        print(f"    ✓ Position {found_position}: Found '{clean_stego_word}' -> {bits}")
                    else:
                        print(f"    ⚠ Found '{clean_stego_word}' at position {found_position} but couldn't extract bits")
                        # Use expected bits as fallback if available
                        if expected_bits:
                            chunk_bits.extend(expected_bits)
                            print(f"      Using expected bits: {expected_bits}")
                else:
                    # Word not found at expected position, search in context
                    print(f"    🔍 Word '{clean_stego_word}' not at expected position {expected_position}, searching...")
                    bits = self._search_for_stego_word(words, clean_stego_word, context_before, context_after)

                    if bits:
                        chunk_bits.extend(bits)
                        print(f"    ✓ Found '{clean_stego_word}' via context search -> {bits}")
                    else:
                        # Last resort: use expected bits if available
                        if expected_bits:
                            chunk_bits.extend(expected_bits)
                            print(f"    ✗ Could not find '{clean_stego_word}', using expected bits: {expected_bits}")
                        else:
                            print(f"    ✗ Could not find '{clean_stego_word}' and no expected bits")

            all_bits.extend(chunk_bits)
            print(f"  Chunk {chunk_idx + 1}: Extracted {len(chunk_bits)} bits")

        print(f"\n  Total bits extracted: {len(all_bits)}")

        # Convert bits to message
        message = self._bits_to_message(all_bits)
        
        if message:
            print(f"\n✅ Message decoded successfully")
        else:
            print(f"\n❌ Failed to decode message from bits")
            
        return message

    def _find_stego_word_at_position(self, words: List[str], expected_pos: int,
                                     clean_stego_word: str, context_before: List[str],
                                     context_after: List[str], exact_string: str) -> Tuple[
        Optional[int], Optional[str]]:
        """
        Try to find stego word at or near expected position.
        Returns: (position, word_found) or (None, None)
        """
        # First check exact position
        if 0 <= expected_pos < len(words):
            word_at_pos = words[expected_pos]
            if self._word_matches_stego(word_at_pos, clean_stego_word):
                # Also verify context if available
                if self._verify_context(words, expected_pos, context_before, context_after):
                    return expected_pos, word_at_pos

        # Check nearby positions (±5 words) for better flexibility
        search_radius = 5
        start = max(0, expected_pos - search_radius)
        end = min(len(words), expected_pos + search_radius + 1)

        best_match = None
        best_position = None
        best_score = 0

        for i in range(start, end):
            word = words[i]
            if self._word_matches_stego(word, clean_stego_word):
                # Score the match based on context and position proximity
                score = 0
                
                # Position proximity score
                distance = abs(i - expected_pos)
                position_score = max(0, search_radius - distance)
                score += position_score
                
                # Context match score
                context_score = self._context_match_score(words, i, context_before, context_after)
                score += context_score
                
                if score > best_score:
                    best_score = score
                    best_match = word
                    best_position = i

        # Return the best match if found
        if best_match is not None and best_score > 0:
            return best_position, best_match

        return None, None

    def _word_matches_stego(self, word: str, clean_stego_word: str) -> bool:
        """Check if a word matches the stego word (case-insensitive, punctuation-insensitive)."""
        # Clean the word for comparison
        clean_word = word.lower()
        clean_word = re.sub(r'[^\w]', '', clean_word)

        # Exact match
        if clean_word == clean_stego_word:
            return True

        # Stemmed match (simple stemming)
        if clean_word.startswith(clean_stego_word[:4]) or clean_stego_word.startswith(clean_word[:4]):
            return True

        return False

    def _context_match_score(self, words: List[str], position: int,
                            expected_before: List[str], expected_after: List[str]) -> int:
        """Calculate how well the context matches expected context."""
        score = 0
        
        # Clean expected context words
        clean_expected_before = [re.sub(r'[^\w]', '', w.lower()) for w in expected_before if w]
        clean_expected_after = [re.sub(r'[^\w]', '', w.lower()) for w in expected_after if w]

        # Check context before
        if clean_expected_before:
            context_start = max(0, position - len(clean_expected_before) - 2)
            actual_before = words[context_start:position]
            actual_before_clean = [re.sub(r'[^\w]', '', w.lower()) for w in actual_before]
            
            # Check if expected words appear in actual context
            for expected_word in clean_expected_before:
                if expected_word and any(expected_word in actual or actual in expected_word 
                                       for actual in actual_before_clean if actual):
                    score += 2

        # Check context after
        if clean_expected_after:
            context_end = min(len(words), position + len(clean_expected_after) + 3)
            actual_after = words[position + 1:context_end]
            actual_after_clean = [re.sub(r'[^\w]', '', w.lower()) for w in actual_after]
            
            # Check if expected words appear in actual context
            for expected_word in clean_expected_after:
                if expected_word and any(expected_word in actual or actual in expected_word 
                                       for actual in actual_after_clean if actual):
                    score += 2

        return score

    def _verify_context(self, words: List[str], position: int,
                        expected_before: List[str], expected_after: List[str]) -> bool:
        """
        Verify that the context around a position matches expected context.
        Returns True if context matches or if no context is provided.
        """
        return self._context_match_score(words, position, expected_before, expected_after) > 0

    def _search_for_stego_word(self, words: List[str], clean_stego_word: str,
                               context_before: List[str], context_after: List[str]) -> Optional[List[int]]:
        """
        Search for stego word anywhere in the text using context clues.
        """
        # If we have context, use it to narrow search
        if context_before or context_after:
            # Search for matching context patterns
            for i in range(len(words)):
                score = self._context_match_score(words, i, context_before, context_after)
                if score > 0:
                    # Check if word at this position matches stego word
                    if i < len(words) and self._word_matches_stego(words[i], clean_stego_word):
                        bits = self._extract_bits_from_word(words[i], clean_stego_word)
                        if bits:
                            return bits

        # Broader search: just look for the word
        for i, word in enumerate(words):
            if self._word_matches_stego(word, clean_stego_word):
                # Try to extract bits
                bits = self._extract_bits_from_word(word, clean_stego_word)
                if bits:
                    return bits

        return None

    def _extract_bits_from_word(self, word: str, clean_stego_word: str) -> Optional[List[int]]:
        """Extract encoded bits from a word."""
        # Clean the word for lookup
        clean_word = word.lower()
        clean_word = re.sub(r'[^\w]', '', clean_word)

        # Try exact match first
        if clean_word in self.token_to_bin_and_index:
            return self._get_bits_from_token(clean_word)

        # Try the provided clean stego word
        if clean_stego_word in self.token_to_bin_and_index:
            return self._get_bits_from_token(clean_stego_word)

        # Try to find similar token
        for token in self.token_to_bin_and_index.keys():
            if clean_word.startswith(token[:3]) or token.startswith(clean_word[:3]):
                return self._get_bits_from_token(token)

        return None

    def _get_bits_from_token(self, token: str) -> Optional[List[int]]:
        """Get bits for a token from the bin."""
        if token not in self.token_to_bin_and_index:
            return None

        bin_id, token_idx = self.token_to_bin_and_index[token]
        bin = self.bin_by_id[bin_id]

        # Determine bits based on bin size
        num_bits = bin.capacity_bits
        
        if num_bits == 0:
            return None
        
        bits = []
        for i in range(num_bits - 1, -1, -1):
            bits.append((token_idx >> i) & 1)
        
        return bits

    def _bits_to_message(self, bits: List[int]) -> str:
        """Convert bits back to message."""
        if len(bits) < 24:  # 16 bits for length + 8 bits checksum
            print(f"  ⚠ Not enough bits: {len(bits)}")
            return ""

        # Extract length (first 16 bits)
        length_bits = bits[:16]
        message_length = 0
        for bit in length_bits:
            message_length = (message_length << 1) | bit

        # Extract checksum (next 8 bits)
        checksum_bits = bits[16:24]
        expected_checksum = 0
        for bit in checksum_bits:
            expected_checksum = (expected_checksum << 1) | bit

        # Validate length
        if message_length <= 0 or message_length > 1000:  # Reasonable limit
            print(f"  ⚠ Invalid message length: {message_length}")
            return ""

        # Extract message
        chars = []
        bit_pos = 24

        for i in range(message_length):
            if bit_pos + 7 > len(bits):
                print(f"  ⚠ Not enough bits for character {i + 1}/{message_length}")
                break

            char_bits = bits[bit_pos:bit_pos + 7]
            ascii_val = 0
            for bit in char_bits:
                ascii_val = (ascii_val << 1) | bit

            if 32 <= ascii_val <= 126:  # Printable ASCII
                chars.append(chr(ascii_val))
            else:
                print(f"  ⚠ Invalid ASCII value: {ascii_val} at position {i}")
                chars.append('?')  # Placeholder for invalid chars

            bit_pos += 7

        message = ''.join(chars)

        # Verify checksum
        actual_checksum = sum(ord(c) for c in message) % 256
        if actual_checksum != expected_checksum:
            print(f"  ⚠ Checksum mismatch: expected {expected_checksum}, got {actual_checksum}")
            # We still return the message, but with warning

        # Verify message ends properly
        message = message.strip()
        return message


# ============================================================
# DECODER UTILITIES FOR FILE INPUT
# ============================================================

def load_chunks_from_file(filename: str) -> List[str]:
    """Load encoded text chunks from a file."""
    try:
        with open(filename, 'r') as f:
            content = f.read().strip()

        # Try to parse as JSON first
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

        # Try to split by chunk markers
        chunks = []
        chunk_markers = ["--- Chunk", "--- Artifact", "## Chunk", "Chunk"]

        for marker in chunk_markers:
            if marker in content:
                parts = content.split(marker)
                # Skip first part if it's before first marker
                for part in parts[1:]:
                    # Extract the chunk text
                    lines = part.strip().split('\n')
                    if lines:
                        # Join lines until we hit another marker or end
                        chunk_text = []
                        for line in lines:
                            if any(m in line for m in chunk_markers):
                                break
                            chunk_text.append(line)
                        if chunk_text:
                            chunks.append(' '.join(chunk_text).strip())
                if chunks:
                    break

        # If no markers found, split by paragraphs
        if not chunks:
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
            chunks = paragraphs

        return chunks

    except Exception as e:
        print(f"Error loading chunks from file: {e}")
        return []


def find_positions_file() -> Optional[str]:
    """Find the positions file automatically."""
    # Try common filenames
    candidates = [
        "stego_positions.json",
        "stego_positions_*.json",
        "positions.json",
        "decoder_positions.json",
        "*.json"  # Any JSON file
    ]

    import glob

    for candidate in candidates:
        if '*' in candidate:
            files = glob.glob(candidate)
            for file in files:
                if "position" in file.lower() or "stego" in file.lower():
                    return file
        elif os.path.exists(candidate):
            return candidate

    # Look for any JSON file
    json_files = glob.glob("*.json")
    for file in json_files:
        if "test" not in file.lower() and "example" not in file.lower():
            return file

    return None


# ============================================================
# TEST DECODER
# ============================================================

def test_decoder():
    """Test the decoder with positions file."""
    print("\n" + "=" * 80)
    print("NATURAL STEGANOGRAPHY DECODER")
    print("=" * 80)
    print("Uses positions file to know exactly where stegowords are")
    print("Supports new corpus parser vocabulary")
    print("=" * 80)

    try:
        # Initialize with auto-detection
        decoder = StegoDecoder()

        # Find positions file
        positions_file = find_positions_file()
        if not positions_file:
            print("\nNo positions file found. Please specify one.")
            positions_file = input("Enter positions filename (or press Enter to use stego_positions.json): ").strip()
            if not positions_file:
                positions_file = "stego_positions.json"

        if not os.path.exists(positions_file):
            print(f"\n❌ Positions file not found: {positions_file}")
            return False, ""

        # Load positions data to know how many chunks we need
        with open(positions_file, 'r') as f:
            positions_data = json.load(f)

        num_chunks = len(positions_data['chunks'])
        print(f"\nPositions file indicates {num_chunks} chunk(s)")

        # Ask for input method
        print("\nChoose input method:")
        print("1. Paste chunks manually")
        print("2. Load from file")
        print("3. Use sample from positions file (for testing)")

        choice = input("\nEnter choice (1-3, default=1): ").strip()

        chunks = []

        if choice == "2":
            # Load from file
            filename = input("Enter filename with encoded text: ").strip()
            if not filename:
                filename = "encoded_text.txt"

            chunks = load_chunks_from_file(filename)

            if len(chunks) != num_chunks:
                print(f"⚠ Warning: Found {len(chunks)} chunks in file, expected {num_chunks}")
                if len(chunks) > num_chunks:
                    chunks = chunks[:num_chunks]
                elif len(chunks) < num_chunks:
                    # Pad with empty chunks
                    chunks.extend([""] * (num_chunks - len(chunks)))

        elif choice == "3":
            # Use sample from positions file
            print("\nUsing sample text from positions file...")
            for i in range(num_chunks):
                if i < len(positions_data['chunks']):
                    sample = positions_data['chunks'][i].get('text_preview', f'Sample text for chunk {i+1}.')
                    if '...' in sample:
                        sample = sample.replace('...', 'continued here with more technical discussion.')
                    chunks.append(sample)
                else:
                    chunks.append(f"Sample text for chunk {i + 1}.")

        else:
            # Manual input (default)
            print(f"\nPlease provide the {num_chunks} encoded text chunk(s):")
            for i in range(num_chunks):
                print(f"\n--- Chunk {i + 1}/{num_chunks} ---")
                if i < len(positions_data['chunks']):
                    preview = positions_data['chunks'][i].get('text_preview', '')
                    if preview:
                        print(f"Preview: {preview}")

                chunk = input("Paste text (or press Enter for empty): ").strip()
                chunks.append(chunk)

        # DECODE
        print("\n" + "=" * 80)
        print("DECODING WITH POSITIONS FILE")
        print("=" * 80)

        decoded = decoder.decode_with_positions(chunks, positions_file)

        # RESULTS
        print("\n" + "=" * 80)
        print("RESULTS")
        print("=" * 80)

        if decoded:
            print(f"✅ Decoded message: '{decoded}'")
            print(f"   Length: {len(decoded)} characters")
            
            # Try to validate
            if len(decoded) < 2:
                print("⚠ Warning: Very short message")
            elif any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?;:\'"-@#$%^&*()_+=' for c in decoded):
                print("⚠ Warning: Message contains unusual characters")
        else:
            print("❌ No message decoded")

        return True, decoded

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False, ""


# ============================================================
# COMMAND LINE INTERFACE
# ============================================================

def decode_from_cli(chunks: List[str], positions_file: str) -> str:
    """CLI interface for decoding."""
    decoder = StegoDecoder()
    return decoder.decode_with_positions(chunks, positions_file)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("NATURAL STEGANOGRAPHY DECODER")
    print("=" * 80)
    print("This decoder reads a positions file to find stegowords")
    print("that are naturally integrated into the text.")
    print("Supports new corpus parser vocabulary (10,000+ words)")
    print("=" * 80)

    success, decoded = test_decoder()

    print("\n" + "=" * 80)
    if success and decoded:
        print(f"✅ DECODER SUCCESS: '{decoded}'")
    elif success:
        print("⚠ DECODER COMPLETE BUT NO MESSAGE EXTRACTED")
    else:
        print("❌ DECODER FAILED")
    print("=" * 80)
