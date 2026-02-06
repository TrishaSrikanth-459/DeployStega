#!/usr/bin/env python3
"""
BYTE-LEVEL CORPUS PARSER
Creates bins optimized for byte-level encoding (256+ words per bin)
"""

import json
import os
import re
import math
import sys
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple, Any
import time

print("=" * 80)
print("BYTE-LEVEL CORPUS PARSER")
print("Creates 256+ word bins for byte-level encoding")
print("=" * 80)


class ByteLevelCorpusProcessor:
    """Processes corpus to create byte-level bins (256+ words each)."""

    def __init__(self, data_path: str = "data/corpus.json"):
        self.data_path = data_path
        self.all_words = []

    def process_corpus(self) -> List[List[str]]:
        """Process corpus and create byte-level bins."""
        print("Processing corpus for byte-level bins...")

        # Load all words from corpus
        self._load_all_words()

        if len(self.all_words) < 10000:
            print(f"⚠ Warning: Only {len(self.all_words)} unique words")
            print("  You may need more corpus data for byte-level encoding")

        # Create byte-level bins
        bins = self._create_byte_level_bins()

        return bins

    def _load_all_words(self):
        """Load all unique words from corpus."""
        words_set = set()
        line_count = 0

        try:
            with open(self.data_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line_count += 1
                    try:
                        data = json.loads(line)
                        text = self._extract_text(data)

                        # Extract words
                        line_words = re.findall(r'\b[a-z][a-z0-9_\-]{2,25}\b', text.lower())
                        words_set.update(line_words)

                    except (json.JSONDecodeError, KeyError, TypeError):
                        continue

            print(f"  Processed {line_count:,} lines")
            print(f"  Found {len(words_set):,} unique words")

            # Remove common stopwords
            stopwords = {
                'the', 'and', 'for', 'are', 'was', 'were', 'this', 'that', 'with',
                'have', 'has', 'had', 'you', 'your', 'they', 'their', 'there',
                'a', 'an', 'to', 'in', 'of', 'it', 'is', 'be', 'as', 'at', 'by',
                'on', 'or', 'but', 'not', 'so', 'if', 'then', 'else', 'do', 'does'
            }

            filtered_words = [w for w in words_set if w not in stopwords]
            self.all_words = sorted(filtered_words)

            print(f"  After stopword removal: {len(self.all_words):,} words")

        except Exception as e:
            print(f"❌ Error loading corpus: {e}")
            # Create synthetic words for testing
            self.all_words = [f"word_{i:04d}" for i in range(20000)]
            print(f"  Created {len(self.all_words)} synthetic words for testing")

    def _extract_text(self, data: Any) -> str:
        """Extract text from JSON data."""
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            text_parts = []
            for key in ['artifact_text', 'text', 'body', 'content', 'message', 'description']:
                if key in data and data[key]:
                    text_parts.append(str(data[key]))
            return ' '.join(text_parts)
        return ""

    def _create_byte_level_bins(self) -> List[List[str]]:
        """Create bins optimized for byte-level encoding."""
        print("\nCreating byte-level bins...")

        all_bins = []
        total_words = len(self.all_words)

        # Strategy: Create bins of different sizes for maximum flexibility
        # 1. Large bins (256+ words) for byte encoding
        # 2. Medium bins (64-128 words) for 6-7 bit encoding
        # 3. Small bins (16-32 words) for 4-5 bit encoding
        # 4. Tiny bins (4-8 words) for fallback

        # Create large bins first (256 words each)
        large_bin_count = min(20, total_words // 256)
        for i in range(large_bin_count):
            start_idx = i * 256
            end_idx = start_idx + 256
            if end_idx <= total_words:
                bin_words = self.all_words[start_idx:end_idx]
                all_bins.append(bin_words)

        print(f"  Created {large_bin_count} large bins (256 words each)")

        # Create medium bins (64 words each)
        remaining_idx = large_bin_count * 256
        medium_bin_count = min(100, (total_words - remaining_idx) // 64)

        for i in range(medium_bin_count):
            start_idx = remaining_idx + i * 64
            end_idx = start_idx + 64
            if end_idx <= total_words:
                bin_words = self.all_words[start_idx:end_idx]
                all_bins.append(bin_words)

        print(f"  Created {medium_bin_count} medium bins (64 words each)")

        # Create small bins (16 words each)
        remaining_idx += medium_bin_count * 64
        small_bin_count = min(200, (total_words - remaining_idx) // 16)

        for i in range(small_bin_count):
            start_idx = remaining_idx + i * 16
            end_idx = start_idx + 16
            if end_idx <= total_words:
                bin_words = self.all_words[start_idx:end_idx]
                all_bins.append(bin_words)

        print(f"  Created {small_bin_count} small bins (16 words each)")

        # Create tiny bins (8 words each) with remaining words
        remaining_idx += small_bin_count * 16
        remaining_words = self.all_words[remaining_idx:]

        tiny_bin_count = min(300, len(remaining_words) // 8)
        for i in range(tiny_bin_count):
            start_idx = i * 8
            end_idx = start_idx + 8
            if end_idx <= len(remaining_words):
                bin_words = remaining_words[start_idx:end_idx]
                all_bins.append(bin_words)

        print(f"  Created {tiny_bin_count} tiny bins (8 words each)")

        # Calculate statistics
        total_bins = len(all_bins)
        total_bin_words = sum(len(b) for b in all_bins)
        unique_bin_words = len(set(word for b in all_bins for word in b))

        print(f"\n📊 BIN STATISTICS:")
        print(f"  Total bins: {total_bins}")
        print(f"  Total words in bins: {total_bin_words}")
        print(f"  Unique words in bins: {unique_bin_words}")

        # Count bins by size
        size_counts = defaultdict(int)
        for bin_words in all_bins:
            size = len(bin_words)
            if size >= 256:
                size_counts['256+'] += 1
            elif size >= 64:
                size_counts['64-255'] += 1
            elif size >= 16:
                size_counts['16-63'] += 1
            else:
                size_counts['2-15'] += 1

        print(f"\n📊 BIN SIZE DISTRIBUTION:")
        for size_range, count in sorted(size_counts.items(), key=lambda x: x[0], reverse=True):
            print(f"  {size_range} words: {count} bins")

        # Calculate encoding capacity
        total_bits = 0
        for bin_words in all_bins:
            if len(bin_words) >= 2:
                bits = int(math.log2(len(bin_words)))
                total_bits += bits

        avg_bits = total_bits / total_bins if total_bins > 0 else 0
        print(f"  Average bits per bin: {avg_bits:.2f}")
        print(f"  Total encoding capacity: {total_bits} bits")

        # Estimate chunks needed for typical message
        typical_message_bits = 200  # ~25 character message
        estimated_chunks = typical_message_bits / (avg_bits * 3) if avg_bits > 0 else 0  # Assume 3 choices per chunk

        print(f"\n🎯 EXPECTED PERFORMANCE:")
        print(f"  For 25-character message (~200 bits):")
        print(f"  Estimated chunks needed: {estimated_chunks:.1f}")
        print(f"  Target: 3-5 chunks (vs original 28)")

        return all_bins


# ============================================================
# MAIN
# ============================================================

def main():
    """Main function to create byte-level bins."""
    print("Creating byte-level bins for steganography...")
    print("Target: Bins with 256+ words for byte-level encoding")
    print("=" * 80)

    start_time = time.time()

    processor = ByteLevelCorpusProcessor("data/corpus.json")
    bins = processor.process_corpus()

    if not bins:
        print("❌ Failed to create bins")
        return

    # Save bins
    output_dir = "token_binning_data"
    os.makedirs(output_dir, exist_ok=True)

    # Save comprehensive version
    output_path = f"{output_dir}/byte_level_bins_comprehensive.json"
    with open(output_path, 'w') as f:
        json.dump({
            'metadata': {
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                'total_bins': len(bins),
                'total_words': sum(len(b) for b in bins),
                'unique_words': len(set(word for b in bins for word in b)),
                'processing_time': time.time() - start_time,
                'purpose': 'byte_level_steganography'
            },
            'bins': bins
        }, f, indent=2)

    # Save simplified version for encoder
    simplified_path = f"{output_dir}/byte_level_bins.json"
    with open(simplified_path, 'w') as f:
        json.dump({'bins': bins}, f, indent=2)

    print(f"\n✅ BYTE-LEVEL BINS CREATED")
    print(f"   Total bins: {len(bins)}")
    print(f"   Time: {time.time() - start_time:.1f}s")
    print(f"   Files saved:")
    print(f"     {output_path} (comprehensive)")
    print(f"     {simplified_path} (simplified for encoder)")


if __name__ == "__main__":
    main()
