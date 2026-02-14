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
# BYTE-LEVEL STEGANOGRAPHY DECODER
# ============================================================

class ByteLevelStegoDecoder:
    """
    Decoder for byte-level steganography.
    Handles byte-level encoding (8 bits per word) instead of bit-level.
    """

    def __init__(self, bins_path: str = None):
        self.bins = []
        self.token_to_bin_and_index = {}  # token -> (bin_id, index_in_bin)
        self.bin_by_id = {}

        # For byte-level decoding
        self.byte_bins = []  # Bins with 256+ words for byte decoding
        self.large_bins = []  # 64-255 words

        # Auto-detect the right bins file
        if bins_path is None:
            bins_path = self._find_byte_bins_file()

        self._load_byte_level_bins(bins_path)

    def _find_byte_bins_file(self) -> str:
        """Find the byte-level bins file automatically."""
        print("Looking for byte-level token bins...")

        # UPDATED: Match the binning pipeline output
        candidates = [
            "token_binning_data/bins_k16.json",  # Primary from binning pipeline
            "token_binning_data/bins_k32.json",
            "token_binning_data/bins_k64.json",
            "token_binning_data/byte_level_bins.json",  # Keep for backward compatibility
            "bins_k16.json",
            "bins_k32.json",
        ]

        for candidate in candidates:
            if os.path.exists(candidate):
                print(f"✓ Found: {candidate}")
                return candidate

        # Look for any JSON file in token_binning_data
        if os.path.exists("token_binning_data"):
            json_files = glob.glob("token_binning_data/*.json")
            for file in json_files:
                print(f"  Found: {file}")
                return file

        # If nothing found, use the default from binning pipeline
        default = "token_binning_data/bins_k16.json"
        print(f"⚠ No bins file found, will try: {default}")
        return default

    def _load_byte_level_bins(self, bins_path: str):
        """Load bins from the binning pipeline output."""
        try:
            print(f"Loading bins from {bins_path}...")

            if not os.path.exists(bins_path):
                raise FileNotFoundError(f"Bins not found at {bins_path}")

            with open(bins_path, 'r', encoding="utf-8") as f:
                data = json.load(f)

            # Handle the actual format from your binning pipeline
            if 'bins' in data:
                bins_data = data['bins']
                print(f"  Loaded bins_k{data.get('k', 16)}.json with {len(bins_data)} bins")
            else:
                bins_data = data
                print(f"  Loaded {len(bins_data)} bins")

            # Load bins - each bin is just a list of tokens
            for bin_id, tokens in enumerate(bins_data):
                if not isinstance(tokens, list):
                    continue

                clean_tokens = []
                for token in tokens:
                    if isinstance(token, str) and token.strip():
                        clean_token = token.strip().lower()
                        clean_token = re.sub(r'[^\w]', '', clean_token)
                        if clean_token and len(clean_token) >= 2:
                            clean_tokens.append(clean_token)

                if len(clean_tokens) >= 2:
                    bin_obj = TokenBin(bin_id=bin_id, tokens=clean_tokens)
                    self.bins.append(bin_obj)
                    self.bin_by_id[bin_id] = bin_obj

                    # Categorize by size
                    if len(clean_tokens) >= 256:
                        self.byte_bins.append(bin_obj)
                    elif len(clean_tokens) >= 64:
                        self.large_bins.append(bin_obj)

                    for idx, token in enumerate(clean_tokens):
                        self.token_to_bin_and_index[token] = (bin_id, idx)

            if not self.bins:
                raise ValueError("No valid bins found")

            print(f"✓ Loaded {len(self.bins)} bins")
            print(f"  - Vocabulary: {len(self.token_to_bin_and_index)} words")
            print(f"  - Byte bins (256+): {len(self.byte_bins)}")
            print(f"  - Large bins (64+): {len(self.large_bins)}")

            total_words = sum(len(b.tokens) for b in self.bins)
            avg_bin_size = total_words / len(self.bins) if self.bins else 0
            print(f"  - Average bin size: {avg_bin_size:.1f} words")

        except Exception as e:
            print(f"✗ Failed to initialize: {e}")
            raise RuntimeError(f"Cannot load bins from {bins_path}: {e}")

    # ============================================================
    # BYTE-LEVEL DECODING
    # ============================================================

    def decode_with_positions(self, chunks: List[str], positions_file: str) -> str:
        """
        Decode byte-level encoded message using positions file.
        """
        print(f"\n📥 BYTE-LEVEL DECODING {len(chunks)} CHUNKS")

        # Load positions data
        try:
            with open(positions_file, 'r') as f:
                positions_data = json.load(f)

            print(f"✓ Loaded positions from: {positions_file}")

            # Check encoding scheme
            metadata = positions_data.get('metadata', {})
            encoding_scheme = metadata.get('encoding', 'byte_level_v1')
            print(f"  Encoding scheme: {encoding_scheme}")

            chunks_data = positions_data.get('chunks', [])
            print(f"  Contains {len(chunks_data)} chunk(s)")

        except Exception as e:
            print(f"✗ Failed to load positions file: {e}")
            return ""

        # Collect all decoded bytes
        all_decoded_bytes = bytearray()

        # Process each chunk
        for chunk_idx, (chunk_text, chunk_data) in enumerate(zip(chunks, chunks_data)):
            if chunk_idx >= len(chunks_data):
                print(f"⚠ Warning: More chunks ({len(chunks)}) than positions data ({len(chunks_data)})")
                break

            print(f"\n  --- Processing Chunk {chunk_idx + 1} ---")

            # Get positions for this chunk
            positions = chunk_data.get('positions', [])
            print(f"  Expected encoded words: {len(positions)}")

            # Tokenize the chunk
            words = chunk_text.split()
            print(f"  Total words in chunk: {len(words)}")

            # Decode bytes from this chunk
            chunk_bytes = self._decode_chunk_bytes(words, positions)
            all_decoded_bytes.extend(chunk_bytes)

            print(f"  Decoded {len(chunk_bytes)} bytes from this chunk")

        # Convert bytes to string
        try:
            message = all_decoded_bytes.decode('utf-8')
            print(f"\n✅ Message decoded successfully: {len(message)} characters")
            return message
        except UnicodeDecodeError:
            print(f"\n⚠ Warning: Could not decode as UTF-8, trying with error handling...")
            message = all_decoded_bytes.decode('utf-8', errors='ignore')
            return message

    def _decode_chunk_bytes(self, words: List[str], positions: List[Dict]) -> bytearray:
        """Decode bytes from a single chunk."""
        decoded_bytes = bytearray()

        for pos_info in positions:
            # Get the target word and its expected index
            target_word = pos_info.get('chosen_word', '')
            target_index = pos_info.get('target_index', 0)
            encoding_type = pos_info.get('encoding_type', 'byte')
            bits = pos_info.get('bits', 8)

            if not target_word:
                print(f"    ⚠ Empty target word, skipping")
                continue

            # Clean the target word for matching
            clean_target = target_word.lower()
            clean_target = re.sub(r'[^\w]', '', clean_target)

            # Find the word in the text
            found_word, found_idx = self._find_word_in_text(words, clean_target)

            if found_word:
                # Decode byte from this word
                decoded_byte = self._decode_byte_from_word(found_word, found_idx, bits)
                if decoded_byte is not None:
                    decoded_bytes.append(decoded_byte)
                    print(f"    ✓ Found '{found_word}' -> byte 0x{decoded_byte:02x}")
                else:
                    print(f"    ⚠ Could not decode byte from '{found_word}'")
            else:
                print(f"    ✗ Could not find word '{clean_target}' in text")
                # Try to use target index as fallback
                if bits == 8:
                    decoded_bytes.append(target_index)
                    print(f"      Using fallback: index {target_index} -> byte 0x{target_index:02x}")

        return decoded_bytes

    def _find_word_in_text(self, words: List[str], target_word: str) -> Tuple[Optional[str], Optional[int]]:
        """Find a word in the text (case-insensitive, punctuation-insensitive)."""
        for idx, word in enumerate(words):
            # Clean the word for comparison
            clean_word = word.lower()
            clean_word = re.sub(r'[^\w]', '', clean_word)

            # Exact match
            if clean_word == target_word:
                return word, idx

            # Partial match (for compound words or slight variations)
            if (clean_word.startswith(target_word[:4]) or
                    target_word.startswith(clean_word[:4]) or
                    clean_word in target_word or target_word in clean_word):
                return word, idx

        return None, None

    def _decode_byte_from_word(self, word: str, position: int, expected_bits: int) -> Optional[int]:
        """Decode a byte from a word using bin lookup."""
        # Clean the word for lookup
        clean_word = word.lower()
        clean_word = re.sub(r'[^\w]', '', clean_word)

        # Look up the word in our bins
        if clean_word in self.token_to_bin_and_index:
            bin_id, token_idx = self.token_to_bin_and_index[clean_word]

            # For byte-level encoding, we use the token index directly as byte value
            # (since bins have 256+ words, index 0-255 represents byte values)
            if expected_bits == 8:
                return token_idx % 256
            else:
                # For other bit lengths, convert appropriately
                max_value = 2 ** expected_bits
                return token_idx % max_value

        # Word not found in bins, try to estimate from position or word itself
        print(f"      Word '{clean_word}' not in bins, using position fallback")

        # Simple hash of the word as fallback
        word_hash = sum(ord(c) for c in clean_word) % 256
        return word_hash

    def decode_without_positions(self, text: str) -> str:
        """
        Attempt to decode without positions file (experimental).
        Looks for words that might be encoded.
        """
        print(f"\n🔍 ATTEMPTING TO DECODE WITHOUT POSITIONS FILE")
        print(f"  Text length: {len(text)} characters")

        words = text.split()
        print(f"  Words in text: {len(words)}")

        # Look for words that are in our bins
        decoded_bytes = bytearray()

        for word in words:
            clean_word = word.lower()
            clean_word = re.sub(r'[^\w]', '', clean_word)

            if clean_word in self.token_to_bin_and_index:
                bin_id, token_idx = self.token_to_bin_and_index[clean_word]
                bin = self.bin_by_id[bin_id]

                # Only use if bin is large enough for byte encoding
                if bin.capacity_bits >= 8:
                    decoded_byte = token_idx % 256
                    decoded_bytes.append(decoded_byte)
                    print(f"  Found encoded word: '{word}' -> byte 0x{decoded_byte:02x}")

        # Try to decode as UTF-8
        try:
            message = decoded_bytes.decode('utf-8')
            print(f"\n  Decoded {len(decoded_bytes)} bytes -> {len(message)} characters")
            return message
        except UnicodeDecodeError:
            # Try with error handling
            message = decoded_bytes.decode('utf-8', errors='ignore')
            print(f"\n  Decoded {len(decoded_bytes)} bytes -> {len(message)} characters (with errors)")
            return message

    def verify_encoding_scheme(self, positions_file: str) -> bool:
        """Verify that positions file matches our encoding scheme."""
        try:
            with open(positions_file, 'r') as f:
                data = json.load(f)

            metadata = data.get('metadata', {})
            encoding = metadata.get('encoding', '')

            # Check if this is byte-level encoding
            byte_level_schemes = ['byte_level', 'ultra_dense', 'forceful']
            is_byte_level = any(scheme in encoding.lower() for scheme in byte_level_schemes)

            if is_byte_level:
                print(f"✓ Positions file uses byte-level encoding: {encoding}")
                return True
            else:
                print(f"⚠ Positions file encoding: {encoding} (may not be byte-level)")
                return False

        except Exception as e:
            print(f"✗ Could not verify encoding scheme: {e}")
            return False


# ============================================================
# DECODER UTILITIES
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

        # Try to split by artifact markers
        chunks = []

        # Common chunk markers in output
        markers = [
            "--- Artifact",
            "--- Chunk",
            "## Chunk",
            "Chunk",
            "Artifact"
        ]

        lines = content.split('\n')
        current_chunk = []
        in_chunk = False

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if line starts a new chunk
            if any(line.startswith(marker) for marker in markers):
                # Save previous chunk if any
                if current_chunk:
                    chunks.append(' '.join(current_chunk))
                    current_chunk = []
                in_chunk = True
                continue

            # Check for separator lines
            if line.startswith('---') or line.startswith('===') or line.startswith('***'):
                if current_chunk:
                    chunks.append(' '.join(current_chunk))
                    current_chunk = []
                in_chunk = False
                continue

            # Add line to current chunk
            if in_chunk or not chunks:
                current_chunk.append(line)

        # Add last chunk if any
        if current_chunk:
            chunks.append(' '.join(current_chunk))

        # If no markers found, split by paragraphs
        if not chunks:
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
            chunks = paragraphs

        print(f"Loaded {len(chunks)} chunks from {filename}")
        return chunks

    except Exception as e:
        print(f"Error loading chunks from file: {e}")
        return []


def find_positions_file() -> Optional[str]:
    """Find the positions file automatically."""
    # Try common filenames from byte-level encoders
    candidates = [
        "byte_level_test.json",
        "ultra_dense_test.json",
        "forceful_test.json",
        "byte_positions_*.json",
        "ultra_dense_positions_*.json",
        "forceful_positions_*.json",
        "stego_positions.json",
        "positions.json"
    ]

    import glob

    for candidate in candidates:
        if '*' in candidate:
            files = glob.glob(candidate)
            for file in files:
                return file
        elif os.path.exists(candidate):
            return candidate

    # Look for any JSON file with "position" or "test" in name
    json_files = glob.glob("*.json")
    for file in json_files:
        if "position" in file.lower() or "test" in file.lower():
            return file

    return None


# ============================================================
# TEST DECODER
# ============================================================

def test_byte_level_decoder():
    """Test the byte-level decoder."""
    print("\n" + "=" * 80)
    print("BYTE-LEVEL STEGANOGRAPHY DECODER")
    print("Decodes byte-level encoded messages (8 bits per word)")
    print("=" * 80)

    try:
        # Initialize with auto-detection
        decoder = ByteLevelStegoDecoder()

        # Find positions file
        positions_file = find_positions_file()
        if not positions_file:
            print("\nNo positions file found. Please specify one.")
            positions_file = input("Enter positions filename: ").strip()
            if not positions_file:
                positions_file = "byte_level_test.json"

        if not os.path.exists(positions_file):
            print(f"\n❌ Positions file not found: {positions_file}")
            print("Trying to decode without positions file...")

            # Get text to decode
            text_file = input("Enter filename with encoded text (or press Enter to skip): ").strip()
            if text_file and os.path.exists(text_file):
                with open(text_file, 'r') as f:
                    text = f.read()
                decoded = decoder.decode_without_positions(text)
            else:
                text = input("Paste encoded text to decode: ").strip()
                decoded = decoder.decode_without_positions(text)

            print("\n" + "=" * 80)
            print(f"Decoded (without positions): '{decoded}'")
            return True, decoded

        # Verify encoding scheme
        decoder.verify_encoding_scheme(positions_file)

        # Load positions data to know how many chunks we need
        with open(positions_file, 'r') as f:
            positions_data = json.load(f)

        chunks_data = positions_data.get('chunks', [])
        num_chunks = len(chunks_data)
        print(f"\nPositions file indicates {num_chunks} chunk(s)")

        # Ask for input method
        print("\nChoose input method:")
        print("1. Paste chunks manually")
        print("2. Load from file")
        print("3. Use text preview from positions file")

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
                    print(f"⚠ Need {num_chunks} chunks, only found {len(chunks)}")
                    # Ask for additional chunks
                    for i in range(len(chunks), num_chunks):
                        print(f"\n--- Additional Chunk {i + 1}/{num_chunks} ---")
                        chunk = input("Paste text: ").strip()
                        chunks.append(chunk)

        elif choice == "3":
            # Use preview from positions file
            print("\nUsing text preview from positions file...")
            for i in range(num_chunks):
                if i < len(chunks_data):
                    preview = chunks_data[i].get('text_preview', '')
                    if preview:
                        # Remove ellipsis if present
                        preview = preview.replace('...', '')
                        chunks.append(preview)
                    else:
                        chunks.append(f"Sample text for chunk {i + 1}.")
                else:
                    chunks.append(f"Sample text for chunk {i + 1}.")

        else:
            # Manual input (default)
            print(f"\nPlease provide the {num_chunks} encoded text chunk(s):")
            for i in range(num_chunks):
                print(f"\n--- Chunk {i + 1}/{num_chunks} ---")
                if i < len(chunks_data):
                    preview = chunks_data[i].get('text_preview', '')
                    if preview:
                        print(f"Preview: {preview}")

                chunk = input("Paste text: ").strip()
                chunks.append(chunk)

        # DECODE
        print("\n" + "=" * 80)
        print("DECODING BYTE-LEVEL ENCODED MESSAGE")
        print("=" * 80)

        decoded = decoder.decode_with_positions(chunks, positions_file)

        # RESULTS
        print("\n" + "=" * 80)
        print("DECODING RESULTS")
        print("=" * 80)

        if decoded:
            print(f"✅ Decoded message: '{decoded}'")
            print(f"   Length: {len(decoded)} characters")
            print(f"   Bytes: {len(decoded.encode('utf-8'))}")

            # Show statistics
            if decoded == "We will meet at 9pm tonight.":
                print("   🎯 CORRECT: Matches test message!")
            else:
                print("   ⚠ Different from expected test message")
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
    decoder = ByteLevelStegoDecoder()
    return decoder.decode_with_positions(chunks, positions_file)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("BYTE-LEVEL STEGANOGRAPHY DECODER")
    print("=" * 80)
    print("This decoder handles byte-level encoding (8 bits per word)")
    print("Requires positions file from encoder for accurate decoding")
    print("=" * 80)

    success, decoded = test_byte_level_decoder()

    print("\n" + "=" * 80)
    if success and decoded:
        print(f"✅ DECODER SUCCESS: '{decoded}'")
    elif success:
        print("⚠ DECODER COMPLETE BUT NO MESSAGE EXTRACTED")
    else:
        print("❌ DECODER FAILED")
    print("=" * 80)
