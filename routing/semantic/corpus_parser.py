#!/usr/bin/env python3
"""
LLM-POWERED SYNONYM BINNING - BATCH API WITH INFINITE RETRY
NO FALLBACKS. NO GIVING UP. Retry forever until LLM outputs valid JSON.
The LLM decides. We wait. We obey.
"""

import os
import re
import json
import argparse
import time
import hashlib
import pickle
from collections import Counter, defaultdict
from typing import List, Tuple, Dict, Optional
import numpy as np
from tqdm import tqdm
from pathlib import Path

# ----------------------------------------------------------------------
# NLP & ML
# ----------------------------------------------------------------------
try:
    import nltk
    from nltk import pos_tag

    nltk.download('averaged_perceptron_tagger_eng', quiet=True)
    NLTK_AVAILABLE = True
except ImportError:
    print("ERROR: install nltk: pip install nltk")
    exit(1)

try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    print("ERROR: install sentence-transformers: pip install sentence-transformers")
    exit(1)

try:
    import hdbscan

    HDBSCAN_AVAILABLE = True
except ImportError:
    print("ERROR: install hdbscan: pip install hdbscan")
    exit(1)

# ----------------------------------------------------------------------
# OpenAI API - BATCH API ONLY
# ----------------------------------------------------------------------
try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    print("ERROR: install openai: pip install openai")
    exit(1)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
if not client.api_key:
    print("ERROR: Please set environment variable OPENAI_API_KEY")
    exit(1)

# ----------------------------------------------------------------------
# Cache for LLM results
# ----------------------------------------------------------------------
FILTER_CACHE_FILE = "llm_filter_cache.pkl"


def load_cache():
    if os.path.exists(FILTER_CACHE_FILE):
        try:
            with open(FILTER_CACHE_FILE, 'rb') as f:
                return pickle.load(f)
        except:
            return {}
    return {}


def save_cache(cache):
    with open(FILTER_CACHE_FILE, 'wb') as f:
        pickle.dump(cache, f)


# ----------------------------------------------------------------------
# AGGRESSIVE JSON EXTRACTION - NO FALLBACKS, JUST EXTRACT OR FAIL
# ----------------------------------------------------------------------
def extract_json_array(text: str) -> Optional[List]:
    """Extract a JSON array from text. Returns None if not found."""
    # Remove markdown code blocks
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)

    # Find the first '[' and last ']'
    start = text.find('[')
    end = text.rfind(']')

    if start == -1 or end == -1:
        return None

    json_str = text[start:end + 1]

    # Clean common issues
    json_str = re.sub(r',\s*]', ']', json_str)
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r'\n', '', json_str)
    json_str = re.sub(r'\s+', ' ', json_str)

    try:
        return json.loads(json_str)
    except:
        try:
            return json.loads(json_str.replace("'", '"'))
        except:
            return None


# ----------------------------------------------------------------------
# PHASE 1: SCAN CORPUS - NO FILTERING, LET LLM DECIDE EVERYTHING
# ----------------------------------------------------------------------
def scan_corpus(data_path: str, min_freq: int = 5) -> Tuple[Counter, List[str]]:
    """Scan corpus and extract ALL tokens for LLM to validate."""
    print("=" * 60)
    print("PHASE 1: Scanning corpus - NO FILTERING")
    print("=" * 60)
    print("The LLM will decide what's valid. No pre-filtering applied.")

    freq = Counter()
    with open(data_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in tqdm(f, desc="Scanning"):
            try:
                d = json.loads(line)
                text = d.get("artifact_text", "")
                # Simple tokenization - split on whitespace and punctuation
                tokens = re.findall(r'\b[a-zA-Z0-9_.-]+\b', text)
                for token in tokens:
                    # Basic cleaning
                    token = token.strip('._-')
                    if 2 <= len(token) <= 50:  # Very broad length constraints
                        freq[token] += 1  # ← REMOVED .lower()!
            except:
                continue

    print(f"Unique tokens before LLM validation: {len(freq):,}")

    # ✅ TAKE ALL WORDS - let LLM decide everything
    candidates = [w for w, c in freq.most_common() if c >= min_freq]
    print(f"Candidates for LLM validation: {len(candidates):,}")

    # Save candidates
    with open("candidates.json", "w") as f:
        json.dump(candidates, f)
    print(f"✓ Saved candidates.json")

    return freq, candidates


# ----------------------------------------------------------------------
# PHASE 2: CREATE AND SUBMIT BATCH - INFINITE RETRY ON FAILURE
# ----------------------------------------------------------------------
def create_validation_batch(candidates: List[str], batch_size: int = 40):  # 🔥 40 WORDS PER BATCH
    """Create a batch file for OpenAI Batch API."""
    cache = load_cache()

    # Only include uncached batches
    uncached_batches = []
    uncached_indices = []

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        cache_key = hashlib.md5(','.join(sorted(batch)).encode()).hexdigest()
        if cache_key not in cache:
            uncached_batches.append(batch)
            uncached_indices.append(i)

    if not uncached_batches:
        print("✓ All batches already cached!")
        return None, []

    print(f"Creating batch file with {len(uncached_batches)} uncached batches...")

    batch_file_path = "batch_requests.jsonl"
    with open(batch_file_path, "w") as f:
        for idx, batch in enumerate(uncached_batches):
            words_str = "\n".join([f"{i + 1}. {w}" for i, w in enumerate(batch)])

            # ============================================================
            # ✅ ULTRA INCLUSIVE PROMPT - LLM DECIDES EVERYTHING
            # ============================================================
            prompt = f"""You are building a high-quality English vocabulary.

            Classify each token as VALID (true) or INVALID (false).

            IMPORTANT - PRIORITIZE BY FREQUENCY:
            - Words appearing EARLIER in the list are MORE FREQUENT in real text
            - Be MORE LIKELY to accept frequent words (top of list)
            - Be MORE STRICT with rare words (bottom of list)

            ========== RULES - FOLLOW EXACTLY ==========

            ✅ VALID - KEEP THESE:
            1. Real English words (run, happy, quickly, the, cat)
            2. Technical terms (refcell, cffi, socketservice, stdpar)
            3. Programming languages, frameworks, libraries (react, django, pytorch)
            4. Compound words that are supposed to be compound (websocket, dockerfile, gitignore) - not (bunnyhappy)
            5. Domain terminology (database, container, kubernetes)
            6. Jargon, slang, informal terms (executive, flamegraph)
            7. Any real word or name [With the exception of those in the INVALID category below].

            ⚠️ ACRONYMS - KEEP ONLY IF WIDELY RECOGNIZED:
            - KEEP: http, tls, ssl, api, sdk, cli, dns, tcp, udp, ip, json, xml
            - REJECT: aaac, aab, aacd, aada, aadb, aadd, aadf, aae, aaeb, aaee, aafa, aafc, aafd

            ❌ INVALID - REJECT THESE - NO EXCEPTIONS. These might be real words, names, or terms or not, but you still REJECT. 
            1. Version numbers: ANY format with dots (1.2.3, v4.5.6, 2023.01.15, 0.1.5, 1.0.0-beta)
            2. Pure numbers: 123, 456, 7890
            3. Hex strings: a1b2c3d4e5, 7e8f9a0b1c2d3e4f, 0x13bf9369
            4. Keyboard gibberish: zhdguvy, ywluzxiilcj, yxnjcmlwdcjdfq
            5. No-vowel strings: qwrtplmn, xzcvbnm, lwzlyxr
            6. File paths: home/user, C:\\windows, /usr/bin
            7. URLs: http://, https://, git@, ssh://
            8. Personal names: benslabbert, fredericbarthelet, antoniovazquezblanco, Emily Sugowski, Amy, Bob
            9. Bot names: anything ending in 'bot' or containing '[bot]'
            10. Anything that looks like it was encoded or is a hash. 
            11. Specific package names, module names, project names that appear personal or aren't publically known/used on the web [For instance, programming-class-101-final]

            ========== DECISION TREE ========== 
            [Just an example, not inclusive of every single decision you might need to make]
            1. Does it look like a version number? → REJECT
            2. Does it contain numbers? → REJECT
            3. Is it pure gibberish? → REJECT
            4. Could it be a real word/term that isn't a url, file path, non-vowel string, hex string, version number, personal name, encoded/hashed text? → KEEP

            Return ONLY a JSON array of {batch_size} booleans in exact order.

            Tokens (ordered by frequency, most frequent first):
            {words_str}"""

            request = {
                "custom_id": f"batch_{uncached_indices[idx]}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "max_tokens": 4000
                }
            }
            f.write(json.dumps(request) + "\n")

    print(f"✓ Created {batch_file_path} with {len(uncached_batches)} requests")
    return batch_file_path, uncached_indices


def submit_batch_with_retry(batch_file_path: str) -> str:
    """Submit batch file to OpenAI. Retry forever on failure."""
    print("\n" + "=" * 60)
    print("PHASE 2: Submitting batch to OpenAI")
    print("=" * 60)

    attempt = 1
    while True:
        try:
            # Upload file
            print(f"Uploading batch file (attempt {attempt})...")
            batch_file = client.files.create(
                file=open(batch_file_path, "rb"),
                purpose="batch"
            )
            print(f"✓ Uploaded: {batch_file.id}")

            # Create batch job
            print("Creating batch job...")
            batch_job = client.batches.create(
                input_file_id=batch_file.id,
                endpoint="/v1/chat/completions",
                completion_window="24h"
            )
            print(f"✓ Batch submitted: {batch_job.id}")
            print(f"  Status: {batch_job.status}")
            print(f"\nBatch ID: {batch_job.id}")
            print("\nNO FALLBACKS. NO GIVING UP. The LLM decides.")
            print("Check status with:")
            print(f"  python3 corpus_parser.py --phase status --batch-id {batch_job.id}")

            return batch_job.id

        except Exception as e:
            print(f"⚠ Submission failed (attempt {attempt}): {e}")
            attempt += 1
            wait_time = min(60 * attempt, 3600)
            print(f"  Retrying in {wait_time} seconds...")
            time.sleep(wait_time)


# ----------------------------------------------------------------------
# PHASE 3: CHECK BATCH STATUS - POLL FOREVER UNTIL COMPLETE
# ----------------------------------------------------------------------
def wait_for_batch_completion(batch_id: str) -> Dict:
    """Poll batch status forever until completed."""
    print("\n" + "=" * 60)
    print(f"PHASE 3: Waiting for batch {batch_id} to complete")
    print("=" * 60)
    print("NO FALLBACKS. NO TIMEOUTS. We wait as long as it takes.")
    print("Press Ctrl+C to check status manually.\n")

    check_interval = 30
    last_status = None

    while True:
        try:
            batch_job = client.batches.retrieve(batch_id)
            status = batch_job.status
            completed = batch_job.request_counts.completed
            total = batch_job.request_counts.total
            failed = batch_job.request_counts.failed

            if status != last_status:
                print(
                    f"[{time.strftime('%H:%M:%S')}] Status: {status.upper()} - {completed}/{total} completed, {failed} failed")
                last_status = status

            if status == "completed":
                print(f"\n✅ Batch completed successfully!")
                print(f"  Total requests: {total}")
                print(f"  Completed: {completed}")
                print(f"  Failed: {failed}")
                return {
                    "status": status,
                    "output_file_id": batch_job.output_file_id,
                    "request_counts": batch_job.request_counts
                }

            if status == "failed":
                print(f"\n❌ Batch failed: {batch_job.errors}")
                print("Creating new batch and resubmitting...")
                return {"status": "failed", "retry": True}

            if completed > 0:
                check_interval = 60
            else:
                check_interval = min(check_interval * 1.5, 300)

            time.sleep(check_interval)

        except KeyboardInterrupt:
            print("\n\n" + "=" * 60)
            print("BATCH STATUS")
            print("=" * 60)
            print(f"Batch ID: {batch_id}")
            print(f"Check later with: python3 corpus_parser.py --phase status --batch-id {batch_id}")
            return {"status": "interrupted", "batch_id": batch_id}

        except Exception as e:
            print(f"⚠ Error checking status: {e}")
            print(f"  Retrying in {check_interval} seconds...")
            time.sleep(check_interval)


# ----------------------------------------------------------------------
# PHASE 4: RETRIEVE AND PROCESS RESULTS - FIXED WITH TRUNCATION
# ----------------------------------------------------------------------
def retrieve_results_with_retry(batch_id: str, candidates: List[str], batch_size: int = 40) -> List[str]:
    """Retrieve and process batch results. Process EVERY batch with truncation."""
    print("\n" + "=" * 60)
    print("PHASE 4: Retrieving batch results")
    print("=" * 60)
    print("NO FALLBACKS. NO GIVING UP. We process EVERY batch.")

    cache = load_cache()
    batches = [candidates[i:i + batch_size] for i in range(0, len(candidates), batch_size)]
    start_indices = list(range(0, len(candidates), batch_size))

    # Get batch job
    batch_job = client.batches.retrieve(batch_id)

    if batch_job.status != "completed":
        print(f"Batch not ready. Status: {batch_job.status}")
        return []

    # Get output file
    result_file_id = batch_job.output_file_id
    result = client.files.content(result_file_id).content

    # Parse ALL results
    results_by_start_index = {}
    for line in result.splitlines():
        if line.strip():
            data = json.loads(line)
            custom_id = data.get("custom_id")

            if custom_id and custom_id.startswith("batch_"):
                try:
                    start_idx = int(custom_id.split("_")[1])
                    response = data.get("response", {})
                    body = response.get("body", {})
                    choices = body.get("choices", [])

                    if choices:
                        content = choices[0].get("message", {}).get("content", "")
                        result_array = extract_json_array(content)
                        if result_array is not None:
                            results_by_start_index[start_idx] = result_array
                            print(f"  ✓ Loaded batch for start index: {start_idx} ({len(result_array)} booleans)")
                except Exception as e:
                    print(f"  ⚠ Error parsing custom_id {custom_id}: {e}")

    # Process batches - CRITICAL FIX: TRUNCATE to batch_size
    valid_words = []
    for batch_idx, start_idx in enumerate(start_indices):
        if start_idx in results_by_start_index:
            result_array = results_by_start_index[start_idx]
            batch = batches[batch_idx]

            if len(result_array) >= len(batch):
                result_array = result_array[:len(batch)]
                cache_key = hashlib.md5(','.join(sorted(batch)).encode()).hexdigest()
                bools = [bool(x) for x in result_array]
                cache[cache_key] = bools

                batch_valid = [batch[i] for i, v in enumerate(bools) if v]
                valid_words.extend(batch_valid)
                print(
                    f"  ✓ Batch {batch_idx} (start={start_idx}): {len(batch_valid)}/{len(batch)} valid (truncated from {len(result_array)})")
            else:
                print(
                    f"  ✗ Batch {batch_idx} (start={start_idx}): array too short ({len(result_array)} vs {len(batch)})")
        else:
            print(f"  ⚠ Batch {batch_idx} (start={start_idx}): not found in results")

    save_cache(cache)
    print(f"\n✅ Processed {len(valid_words)} valid words from {len(results_by_start_index)} batches")
    return valid_words


# ----------------------------------------------------------------------
# PHASE 5: CLUSTERING AND BINNING - NO API CALLS
# ============================================================================
# Creates simple alphabetical bins
# ============================================================================
def cluster_and_bin(valid_words: List[str], freq: Counter, args):
    """Create simple alphabetical bins."""
    print("\n" + "=" * 60)
    print("PHASE 5: Creating bins")
    print("=" * 60)

    if not valid_words:
        print("❌ ERROR: No valid words to bin!")
        return []

    # Build vocabulary - take top N valid words by frequency
    valid_freq = Counter({w: freq[w] for w in valid_words})
    vocab = [w for w, c in valid_freq.most_common(min(args.max_vocab, len(valid_words)))]
    print(f"Vocabulary size: {len(vocab):,}")

    # Alphabetical binning
    print("\nCreating alphabetical bins...")
    sorted_vocab = sorted(vocab)
    all_bins = []

    for i in range(0, len(sorted_vocab), args.bin_size):
        chunk = sorted_vocab[i:i + args.bin_size]
        if len(chunk) >= 4:
            all_bins.append(chunk)

    print(f"Created {len(all_bins)} bins of size ~{args.bin_size}")

    # Calculate coverage
    binned_words = set([word for bin in all_bins for word in bin])
    coverage = len(binned_words) / len(vocab) * 100 if vocab else 0

    print(f"\n{'=' * 60}")
    print(f"FINAL: {len(binned_words):,}/{len(vocab):,} words in bins ({coverage:.1f}%)")
    print(f"Total bins: {len(all_bins):,}")

    # Save
    os.makedirs(args.out, exist_ok=True)
    output_file = os.path.join(args.out, f"bins_k{args.bin_size}.json")
    with open(output_file, "w") as f:
        json.dump({
            "k": args.bin_size,
            "vocab_size": len(vocab),
            "bins": all_bins
        }, f, indent=2)
    print(f"\n✓ Saved to {output_file}")

    return all_bins


# ----------------------------------------------------------------------
# MAIN - PHASE-BASED EXECUTION
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/corpus.json")
    parser.add_argument("--out", default="token_binning_data")
    parser.add_argument("--max-vocab", type=int, default=35000)
    parser.add_argument("--bin-size", type=int, default=16)
    parser.add_argument("--min-freq", type=int, default=5)

    parser.add_argument("--phase",
                        choices=["scan", "submit", "wait", "status", "retrieve", "cluster", "full"],
                        default="full")
    parser.add_argument("--batch-id", type=str, help="Batch ID for status/retrieve/wait")
    parser.add_argument("--no-cluster", action="store_true", help="Skip clustering phase")

    args = parser.parse_args()

    BATCH_SIZE = 40  # 🔥 40 WORDS PER BATCH - RELIABLE

    if args.phase == "scan":
        scan_corpus(args.data, args.min_freq)
        print("\nNext: python3 corpus_parser.py --phase submit")

    elif args.phase == "submit":
        if not os.path.exists("candidates.json"):
            print("ERROR: No candidates.json found. Run --phase scan first.")
            return

        with open("candidates.json", "r") as f:
            candidates = json.load(f)

        batch_file, indices = create_validation_batch(candidates, batch_size=BATCH_SIZE)
        if batch_file:
            batch_id = submit_batch_with_retry(batch_file)
            print(f"\nBATCH ID: {batch_id}")

    elif args.phase == "wait":
        if not args.batch_id:
            print("ERROR: --batch-id required")
            return
        wait_for_batch_completion(args.batch_id)

    elif args.phase == "status":
        if not args.batch_id:
            print("ERROR: --batch-id required")
            return
        try:
            batch_job = client.batches.retrieve(args.batch_id)
            print("\n" + "=" * 60)
            print("BATCH STATUS")
            print("=" * 60)
            print(f"Batch ID: {batch_job.id}")
            print(f"Status: {batch_job.status.upper()}")
            print(f"Created: {time.ctime(batch_job.created_at)}")
            if batch_job.completed_at:
                print(f"Completed: {time.ctime(batch_job.completed_at)}")
            print(f"\nRequests: {batch_job.request_counts.total}")
            print(f"Completed: {batch_job.request_counts.completed}")
            print(f"Failed: {batch_job.request_counts.failed}")
            if batch_job.status == "completed":
                print(f"\n✅ Ready to retrieve! Output file: {batch_job.output_file_id}")
                print(f"Next: python3 corpus_parser.py --phase retrieve --batch-id {batch_job.id}")
        except Exception as e:
            print(f"ERROR: {e}")

    elif args.phase == "retrieve":
        if not args.batch_id:
            print("ERROR: --batch-id required")
            return
        if not os.path.exists("candidates.json"):
            print("ERROR: No candidates.json found")
            return

        with open("candidates.json", "r") as f:
            candidates = json.load(f)

        valid_words = retrieve_results_with_retry(args.batch_id, candidates, batch_size=BATCH_SIZE)

        if valid_words:
            with open("valid_words.json", "w") as f:
                json.dump(valid_words, f)
            print(f"\n✓ Saved {len(valid_words)} valid words to valid_words.json")

    elif args.phase == "cluster":
        if not os.path.exists("valid_words.json"):
            print("ERROR: No valid_words.json found. Run --phase retrieve first.")
            return
        if not os.path.exists("candidates.json"):
            print("ERROR: No candidates.json found")
            return

        with open("valid_words.json", "r") as f:
            valid_words = json.load(f)
        with open("candidates.json", "r") as f:
            candidates = json.load(f)

        freq = Counter({w: i for i, w in enumerate(candidates)})
        cluster_and_bin(valid_words, freq, args)

    elif args.phase == "full":
        print("\n" + "=" * 60)
        print("FULL PIPELINE - BATCH API ONLY")
        print("=" * 60)
        print("NO FALLBACKS. NO GIVING UP. The LLM decides.")
        print("=" * 60)

        # Scan ALL words
        freq, candidates = scan_corpus(args.data, args.min_freq)

        # Check cache with consistent batch size
        cache = load_cache()
        all_cached = True
        for i in range(0, len(candidates), BATCH_SIZE):
            batch = candidates[i:i + BATCH_SIZE]
            cache_key = hashlib.md5(','.join(sorted(batch)).encode()).hexdigest()
            if cache_key not in cache:
                all_cached = False
                break

        if all_cached:
            print("\n✓ All batches already cached! Skipping batch submission.")
            valid_words = []
            for i in range(0, len(candidates), BATCH_SIZE):
                batch = candidates[i:i + BATCH_SIZE]
                cache_key = hashlib.md5(','.join(sorted(batch)).encode()).hexdigest()
                bools = cache[cache_key]
                batch_valid = [batch[j] for j, v in enumerate(bools) if v]
                valid_words.extend(batch_valid)

            with open("valid_words.json", "w") as f:
                json.dump(valid_words, f)
            print(f"✓ Reconstructed {len(valid_words)} valid words from cache")

        else:
            batch_file, indices = create_validation_batch(candidates, batch_size=BATCH_SIZE)
            if batch_file:
                batch_id = submit_batch_with_retry(batch_file)
                print(f"\nBATCH ID: {batch_id}")
                print("\n✅ Batch submitted. Run these commands when complete:")
                print(f"  python3 corpus_parser.py --phase status --batch-id {batch_id}")
                print(f"  python3 corpus_parser.py --phase retrieve --batch-id {batch_id}")
                print(f"  python3 corpus_parser.py --phase cluster")
                return

        if not args.no_cluster and os.path.exists("valid_words.json"):
            with open("valid_words.json", "r") as f:
                valid_words = json.load(f)
            cluster_and_bin(valid_words, freq, args)


if __name__ == "__main__":
    main()
