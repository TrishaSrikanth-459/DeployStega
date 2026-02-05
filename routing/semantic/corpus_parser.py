#!/usr/bin/env python3
"""
BULLETPROOF CORPUS PARSER v3.0 - Extracts MASSIVE vocabulary from actual GitHub corpus data
EXPANDED VOCABULARY - Targets 10,000+ words from REAL GitHub artifacts
"""

import json
import pickle
import numpy as np
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple, Any
import math
import os
import re
import sys
import gzip
from tqdm import tqdm

# ============================================================
# BULLETPROOF NLTK SETUP
# ============================================================

print("=" * 80)
print("BULLETPROOF CORPUS PARSER v3.0 - MASSIVE REAL VOCABULARY EXTRACTION")
print("=" * 80)
print("\nSetting up NLTK...")

try:
    import nltk
    from nltk.corpus import wordnet
    from nltk import pos_tag
except ImportError:
    print("❌ NLTK not installed. Installing...")
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "nltk"])
    import nltk
    from nltk.corpus import wordnet
    from nltk import pos_tag

# Download required NLTK data
required_packages = ['averaged_perceptron_tagger', 'punkt', 'wordnet']
for package in required_packages:
    try:
        nltk.data.find(package)
    except LookupError:
        nltk.download(package, quiet=True)

print("✓ NLTK setup complete")

# ============================================================
# OTHER IMPORTS
# ============================================================

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity

    print("✓ Sentence transformers and sklearn loaded")
except ImportError:
    print("❌ Missing dependencies. Installing...")
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "sentence-transformers", "scikit-learn"])
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity


# ============================================================
# MASSIVE VOCABULARY EXTRACTOR
# ============================================================

class MassiveVocabularyExtractor:
    """Extracts ALL vocabulary from GitHub corpus data."""

    def __init__(self, data_path: str = "data/corpus.json"):
        self.data_path = data_path
        self.all_words_counter = Counter()
        self.unique_words = set()
        self.total_artifacts = 0
        self.total_words = 0

        # Technical stopwords (basic ones only - we want to keep MOST technical words)
        self.stopwords = {
            'the', 'and', 'for', 'are', 'was', 'were', 'this', 'that', 'with', 'from',
            'have', 'has', 'had', 'you', 'your', 'they', 'their', 'there', 'what',
            'which', 'when', 'where', 'why', 'how', 'would', 'could', 'should',
            'about', 'into', 'over', 'under', 'between', 'through', 'during',
            'before', 'after', 'above', 'below', 'since', 'until', 'upon',
            'a', 'an', 'to', 'in', 'of', 'it', 'is', 'be', 'as', 'at', 'by',
            'on', 'or', 'but', 'not', 'so', 'if', 'then', 'else', 'do', 'does',
            'did', 'can', 'will', 'shall', 'may', 'might', 'must', 'ought'
        }

    def extract_vocabulary(self) -> Tuple[Counter, Set]:
        """Extract ALL vocabulary from the GitHub corpus."""
        print("\n" + "=" * 80)
        print("EXTRACTING VOCABULARY FROM GITHUB CORPUS")
        print("=" * 80)

        if not os.path.exists(self.data_path):
            print(f"❌ File not found: {self.data_path}")
            return self.all_words_counter, self.unique_words

        # Check file size
        file_size = os.path.getsize(self.data_path)
        print(f"Corpus file size: {file_size:,} bytes")

        # Count lines first for progress bar
        print("Counting lines...")
        with open(self.data_path, 'r', encoding='utf-8', errors='ignore') as f:
            total_lines = sum(1 for _ in f)

        print(f"\nProcessing {total_lines:,} GitHub artifacts...")

        # Process each line
        with open(self.data_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(tqdm(f, total=total_lines, desc="Extracting words")):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    self.total_artifacts += 1

                    # Extract text from all possible fields
                    text_parts = []

                    # Check various fields that might contain text
                    if isinstance(data, dict):
                        for field in ['artifact_text', 'text', 'body', 'content', 'message',
                                      'comment', 'description', 'title', 'name', 'issue', 'pr']:
                            if field in data and data[field]:
                                text_parts.append(str(data[field]))

                    # Also try to extract from nested structures
                    if isinstance(data, dict) and 'data' in data and isinstance(data['data'], dict):
                        for field in ['artifact_text', 'text', 'body', 'content']:
                            if field in data['data'] and data['data'][field]:
                                text_parts.append(str(data['data'][field]))

                    # Combine all text
                    if text_parts:
                        full_text = ' '.join(text_parts)
                        self._extract_words_from_text(full_text)

                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    # Skip malformed lines
                    continue

                # Progress update
                if line_num % 10000 == 0 and line_num > 0:
                    print(f"  Processed {line_num:,} lines, found {len(self.unique_words):,} unique words...")

        print(f"\n✓ Extracted {len(self.unique_words):,} unique words from {self.total_artifacts:,} artifacts")
        print(f"  Total word occurrences: {self.total_words:,}")

        return self.all_words_counter, self.unique_words

    def _extract_words_from_text(self, text: str):
        """Extract all valid words from text."""
        # Convert to lowercase
        text = text.lower()

        # Remove code blocks, URLs, and special characters but keep technical words
        # We want to keep words with underscores, hyphens, numbers (like "api_v2", "test-123")
        text = re.sub(r'```.*?```', ' ', text, flags=re.DOTALL)  # Remove code blocks
        text = re.sub(r'`.*?`', ' ', text)  # Remove inline code
        text = re.sub(r'http\S+', ' ', text)  # Remove URLs
        text = re.sub(r'[^\w\s\-_@#&]', ' ', text)  # Keep words, spaces, hyphens, underscores

        # Extract tokens - including ones with underscores, hyphens, and numbers
        # This captures: api_v2, test-123, GitHub, node.js, etc.
        tokens = re.findall(r'[a-zA-Z][a-zA-Z0-9_\-]*[a-zA-Z0-9]', text)

        for token in tokens:
            # Filter: at least 3 chars, not a stopword, not all numeric
            if (len(token) >= 3 and
                    token not in self.stopwords and
                    not token.isnumeric() and
                    not re.match(r'^\d+$', token)):

                # Clean up the token
                token_clean = self._clean_token(token)
                if token_clean and len(token_clean) >= 3:
                    self.all_words_counter[token_clean] += 1
                    self.unique_words.add(token_clean)
                    self.total_words += 1

    def _clean_token(self, token: str) -> str:
        """Clean a token while preserving technical terms."""
        # Remove trailing/leading special chars but keep internal ones
        token = token.strip('-_@#&')

        # If token contains underscores or hyphens, split and check parts
        if '_' in token or '-' in token:
            # Keep compound words as is (like api_v2, user-friendly)
            return token

        return token

    def get_top_words(self, n: int = 50000, min_freq: int = 2) -> List[str]:
        """Get top N words with minimum frequency."""
        print(f"\nSelecting top {n:,} words (frequency >= {min_freq})...")

        top_words = []
        for word, freq in self.all_words_counter.most_common():
            if freq >= min_freq:
                top_words.append(word)
                if len(top_words) >= n:
                    break

        print(f"Selected {len(top_words):,} words with frequency >= {min_freq}")
        return top_words

    def analyze_vocabulary(self):
        """Analyze the extracted vocabulary."""
        print("\n" + "=" * 80)
        print("VOCABULARY ANALYSIS")
        print("=" * 80)

        if not self.all_words_counter:
            print("No vocabulary extracted yet.")
            return

        total_unique = len(self.unique_words)
        total_occurrences = sum(self.all_words_counter.values())

        print(f"\nTotal unique words: {total_unique:,}")
        print(f"Total word occurrences: {total_occurrences:,}")
        print(f"Average frequency: {total_occurrences / total_unique:.2f}")

        # Show most common words
        print(f"\nTop 20 most frequent words:")
        for word, freq in self.all_words_counter.most_common(20):
            print(f"  {word}: {freq:,}")

        # Show frequency distribution
        print(f"\nFrequency distribution:")
        freq_ranges = [(1, 1), (2, 5), (6, 10), (11, 50), (51, 100), (101, 1000), (1001, None)]

        for min_f, max_f in freq_ranges:
            if max_f:
                count = sum(1 for freq in self.all_words_counter.values() if min_f <= freq <= max_f)
            else:
                count = sum(1 for freq in self.all_words_counter.values() if freq >= min_f)
            print(f"  Frequency {min_f}-{max_f if max_f else '∞'}: {count:,} words")

        # Word length distribution
        print(f"\nWord length distribution:")
        length_counts = defaultdict(int)
        for word in self.unique_words:
            length_counts[len(word)] += 1

        for length in sorted(length_counts.keys()):
            if length <= 15:
                print(f"  Length {length}: {length_counts[length]:,} words")
            elif length == 16:
                print(
                    f"  Length 16+: {sum(length_counts[l] for l in range(16, max(length_counts.keys()) + 1)):,} words")


# ============================================================
# MASSIVE SYNONYM BIN CREATOR
# ============================================================

class MassiveSynonymBinCreator:
    """Creates massive synonym bins from extracted vocabulary."""

    def __init__(self):
        print("\nLoading sentence transformer model for semantic analysis...")
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        print("✓ Model loaded")

        # POS mapping
        self.pos_map = {
            'NN': 'NOUN', 'NNS': 'NOUN', 'NNP': 'NOUN', 'NNPS': 'NOUN',
            'VB': 'VERB', 'VBD': 'VERB', 'VBG': 'VERB', 'VBN': 'VERB',
            'VBP': 'VERB', 'VBZ': 'VERB', 'MD': 'VERB',
            'JJ': 'ADJ', 'JJR': 'ADJ', 'JJS': 'ADJ',
            'RB': 'ADV', 'RBR': 'ADV', 'RBS': 'ADV',
            'IN': 'OTHER', 'TO': 'OTHER', 'DT': 'OTHER', 'PDT': 'OTHER',
            'WDT': 'OTHER', 'PRP': 'OTHER', 'PRP$': 'OTHER', 'WP': 'OTHER',
            'CC': 'OTHER', 'CD': 'OTHER', 'EX': 'OTHER', 'FW': 'OTHER',
            'LS': 'OTHER', 'POS': 'OTHER', 'RP': 'OTHER', 'SYM': 'OTHER',
            'UH': 'OTHER', 'WRB': 'OTHER'
        }

        self.wordnet_pos_map = {
            'n': 'NOUN',
            'v': 'VERB',
            'a': 'ADJ',
            's': 'ADJ',
            'r': 'ADV'
        }

        # Technical terms that might not be in WordNet but are valid
        self.technical_terms = set()

    def get_pos_for_word(self, word: str) -> Tuple[str, str]:
        """Get POS tag for a word."""
        try:
            # Try NLTK POS tagging
            tagged = pos_tag([word])
            if tagged:
                penn_tag = tagged[0][1]
                simplified_pos = self.pos_map.get(penn_tag, 'NOUN')
                if simplified_pos != 'OTHER':
                    return simplified_pos, penn_tag
        except:
            pass

        # Fallback to WordNet
        try:
            synsets = wordnet.synsets(word)
            if synsets:
                wordnet_pos = synsets[0].pos()
                simplified_pos = self.wordnet_pos_map.get(wordnet_pos, 'NOUN')
                penn_tag = {'NOUN': 'NN', 'VERB': 'VB', 'ADJ': 'JJ', 'ADV': 'RB'}.get(simplified_pos, 'NN')
                return simplified_pos, penn_tag
        except:
            pass

        # Default to noun for technical terms
        return 'NOUN', 'NN'

    def find_synonyms_with_context(self, word: str, top_words: List[str],
                                   min_similarity: float = 0.6) -> List[str]:
        """Find synonyms using embeddings and context."""
        if not word or len(word) < 3:
            return []

        # Get candidate synonyms from top words
        candidates = []
        for candidate in top_words:
            if (candidate != word and
                    len(candidate) >= 3 and
                    not candidate.startswith(word) and
                    not word.startswith(candidate)):

                # Quick filter by POS
                pos1, _ = self.get_pos_for_word(word)
                pos2, _ = self.get_pos_for_word(candidate)
                if pos1 == pos2:
                    candidates.append(candidate)

                if len(candidates) >= 1000:  # Limit for performance
                    break

        if not candidates:
            return []

        # Use embeddings to find semantic similarity
        try:
            # Include the target word
            all_words = [word] + candidates

            # Batch processing for speed
            embeddings = self.embedding_model.encode(all_words, show_progress_bar=False)

            # Calculate similarities
            target_embedding = embeddings[0:1]
            candidate_embeddings = embeddings[1:]

            similarities = cosine_similarity(target_embedding, candidate_embeddings)[0]

            # Filter by similarity
            similar_words = []
            for cand, sim in zip(candidates, similarities):
                if sim >= min_similarity:
                    similar_words.append((cand, sim))

            # Sort by similarity and return top
            similar_words.sort(key=lambda x: x[1], reverse=True)
            return [word for word, _ in similar_words[:15]]  # Top 15

        except Exception as e:
            return []

    def create_massive_bins(self, top_words: List[str], target_bins: int = 3000) -> List[Dict]:
        """Create massive synonym bins."""
        print("\n" + "=" * 80)
        print("CREATING MASSIVE SYNONYM BINS")
        print("=" * 80)

        used_words = set()
        bins = []

        print(f"Processing {len(top_words):,} words to create ~{target_bins:,} bins...")

        # Process words in batches for progress tracking
        batch_size = 1000
        for batch_start in tqdm(range(0, len(top_words), batch_size), desc="Creating bins"):
            batch_end = min(batch_start + batch_size, len(top_words))
            batch_words = top_words[batch_start:batch_end]

            for word in batch_words:
                if word in used_words:
                    continue

                # Skip very common words that might be stopwords
                if len(word) < 4:
                    continue

                # Get POS
                pos, _ = self.get_pos_for_word(word)
                if pos == 'OTHER':
                    continue

                # Find synonyms
                synonyms = self.find_synonyms_with_context(word, top_words, min_similarity=0.6)

                if len(synonyms) >= 2:  # Need at least 2 synonyms for a bin
                    # Create bin
                    bin_words = [word] + synonyms[:7]  # Up to 8 words per bin

                    # Mark words as used
                    for w in bin_words:
                        used_words.add(w)

                    # Calculate semantic coherence
                    try:
                        embeddings = self.embedding_model.encode(bin_words, show_progress_bar=False)
                        similarities = cosine_similarity(embeddings)
                        semantic_coherence = float(np.mean(similarities))
                    except:
                        semantic_coherence = 0.6

                    # Create bin dict
                    bin_dict = {
                        'bin_id': len(bins),
                        'tokens': bin_words,
                        'pos': pos,
                        'semantic_coherence': semantic_coherence,
                        'size': len(bin_words),
                        'capacity_bits': int(math.log2(len(bin_words))) if len(bin_words) > 1 else 1
                    }

                    bins.append(bin_dict)

                # Stop if we have enough bins
                if len(bins) >= target_bins * 1.2:  # 20% extra for filtering
                    break

            if len(bins) >= target_bins * 1.2:
                break

        print(f"\nCreated {len(bins):,} candidate bins")

        # Filter by quality
        print("Filtering bins by quality...")
        quality_bins = []
        for bin in bins:
            if (len(bin['tokens']) >= 3 and
                    bin['semantic_coherence'] >= 0.6 and
                    bin['capacity_bits'] >= 1):
                quality_bins.append(bin)

        print(f"Kept {len(quality_bins):,} high-quality bins")

        return quality_bins

    def analyze_bins(self, bins: List[Dict]):
        """Analyze the created bins."""
        print("\n" + "=" * 80)
        print("BIN ANALYSIS")
        print("=" * 80)

        if not bins:
            print("No bins to analyze")
            return

        total_words = sum(len(b['tokens']) for b in bins)
        unique_words = set()
        for b in bins:
            unique_words.update(b['tokens'])

        sizes = [len(b['tokens']) for b in bins]
        coherences = [b['semantic_coherence'] for b in bins]

        print(f"\nTotal bins: {len(bins):,}")
        print(f"Total words in bins: {total_words:,}")
        print(f"Unique words in bins: {len(unique_words):,}")
        print(f"Bin size - Avg: {np.mean(sizes):.1f}, Min: {min(sizes)}, Max: {max(sizes)}")
        print(
            f"Semantic coherence - Avg: {np.mean(coherences):.3f}, Min: {min(coherences):.3f}, Max: {max(coherences):.3f}")

        # POS distribution
        pos_counts = Counter([b['pos'] for b in bins])
        print(f"\nPOS Distribution:")
        for pos, count in pos_counts.most_common():
            print(f"  {pos}: {count:,}")

        # Bit capacity distribution
        bit_counts = Counter([b['capacity_bits'] for b in bins])
        print(f"\nBit Capacity Distribution:")
        for bits, count in sorted(bit_counts.items()):
            print(f"  {bits} bits: {count:,} bins")

        # Example bins
        print(f"\nExample Bins (first 3):")
        for i, bin in enumerate(bins[:3]):
            print(f"\n  Bin {i}: {bin['pos']}, coherence={bin['semantic_coherence']:.3f}, {len(bin['tokens'])} words")
            print(f"    Words: {', '.join(bin['tokens'][:8])}")


# ============================================================
# MAIN PIPELINE
# ============================================================

def main():
    """Main execution pipeline."""
    print("=" * 80)
    print("MASSIVE VOCABULARY EXTRACTION PIPELINE")
    print("=" * 80)

    # Step 1: Extract ALL vocabulary from corpus
    extractor = MassiveVocabularyExtractor(data_path="data/corpus.json")
    word_counter, unique_words = extractor.extract_vocabulary()

    if not unique_words:
        print("❌ Failed to extract vocabulary")
        return

    # Analyze vocabulary
    extractor.analyze_vocabulary()

    # Step 2: Get top words for bin creation
    top_words = extractor.get_top_words(n=50000, min_freq=2)

    if len(top_words) < 1000:
        print(f"❌ Only found {len(top_words):,} words. Need more data.")
        return

    # Step 3: Create massive synonym bins
    bin_creator = MassiveSynonymBinCreator()
    bins = bin_creator.create_massive_bins(top_words, target_bins=3000)

    if not bins:
        print("❌ Failed to create bins")
        return

    # Analyze bins
    bin_creator.analyze_bins(bins)

    # Step 4: Save results
    print("\n" + "=" * 80)
    print("SAVING RESULTS")
    print("=" * 80)

    output_dir = "token_binning_data"
    os.makedirs(output_dir, exist_ok=True)

    # Save as JSON
    output_data = {
        'metadata': {
            'total_bins': len(bins),
            'total_unique_words': len(set(word for b in bins for word in b['tokens'])),
            'total_words_in_bins': sum(len(b['tokens']) for b in bins),
            'avg_bin_size': float(np.mean([len(b['tokens']) for b in bins])),
            'avg_semantic_coherence': float(np.mean([b['semantic_coherence'] for b in bins])),
            'extraction_timestamp': "2024-01-01T00:00:00Z"
        },
        'bins': bins
    }

    json_path = f"{output_dir}/massive_token_bins.json"
    with open(json_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    # Also save as simplified format for stego encoder
    simplified_bins = [b['tokens'] for b in bins]
    simplified_path = f"{output_dir}/bulletproof_token_bins.json"
    with open(simplified_path, 'w') as f:
        json.dump({'bins': simplified_bins}, f, indent=2)

    print(f"\n✓ Saved {len(bins):,} bins to:")
    print(f"  {json_path}")
    print(f"  {simplified_path}")

    # Step 5: Create vocabulary summary
    all_bin_words = set()
    for b in bins:
        all_bin_words.update(b['tokens'])

    vocab_path = f"{output_dir}/vocabulary_summary.txt"
    with open(vocab_path, 'w') as f:
        f.write(f"TOTAL VOCABULARY EXTRACTED\n")
        f.write(f"===========================\n")
        f.write(f"Total unique words in corpus: {len(unique_words):,}\n")
        f.write(f"Total words in bins: {len(all_bin_words):,}\n")
        f.write(f"Total bins created: {len(bins):,}\n\n")

        f.write(f"TOP 100 WORDS BY FREQUENCY\n")
        f.write(f"===========================\n")
        for word, freq in word_counter.most_common(100):
            f.write(f"{word}: {freq}\n")

        f.write(f"\nALL WORDS IN BINS ({len(all_bin_words)})\n")
        f.write(f"========================\n")
        for word in sorted(all_bin_words):
            f.write(f"{word}\n")

    print(f"  {vocab_path}")

    print("\n" + "=" * 80)
    print("✅ PIPELINE COMPLETE")
    print("=" * 80)

    # Final statistics
    total_bin_words = sum(len(b['tokens']) for b in bins)
    unique_bin_words = len(set(word for b in bins for word in b['tokens']))

    print(f"\nFINAL STATISTICS:")
    print(f"  • Total bins: {len(bins):,}")
    print(f"  • Total words in bins: {total_bin_words:,}")
    print(f"  • Unique words for steganography: {unique_bin_words:,}")
    print(f"  • Expected bit capacity per bin: 1-3 bits")

    if unique_bin_words < 10000:
        print(f"\n⚠ WARNING: Only {unique_bin_words:,} unique words.")
        print("  To get more words, consider:")
        print("  1. Using a larger corpus.json file")
        print("  2. Lowering the frequency threshold (currently 2)")
        print("  3. Including more fields from the JSON data")
    else:
        print(f"\n✅ SUCCESS: {unique_bin_words:,} unique words available for steganography!")
        print("  This should eliminate word repetition issues.")


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error in pipeline: {e}")
        import traceback

        traceback.print_exc()
