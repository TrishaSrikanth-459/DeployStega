#!/usr/bin/env python3
"""
run_baselines.py — DeployStega baseline evaluations

Sub-commands:
  adversary   TS-CNN steganalysis classifier (adversary-side baseline)
  covert      NLS/Huffman encoder swap + eval  (covert-side baseline)

Adversary baseline:
  Runs TS-CNN (CNN over token embeddings, Yang et al. 2020) on existing
  benign/covert traces. Only TS-CNN is run here — BERT runs separately.

  Example:
    python scripts/run_baselines.py adversary \\
        --benign-dir benign_traces \\
        --covert-dir experiments/covert_traces_full/sender \\
        --output-dir baseline_results/ts_cnn

Covert encoder baseline:
  Takes existing covert sender traces, replaces semantic_text with
  NLS Huffman-over-GPT2 generated text (keeping routing/behavioral
  structure identical), then runs adversarial_evaluation.
  If our system gives lower epsilon than NLS, behavior traces help.

  Example:
    python scripts/run_baselines.py covert \\
        --covert-dir experiments/covert_traces_full/sender \\
        --benign-dir benign_traces \\
        --output-dir baseline_results/nls_encoder \\
        --smoke
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
import os
import random
import sys
from argparse import Namespace
from collections import defaultdict
from functools import total_ordering
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import auc, roc_curve
from torch.utils.data import DataLoader, Dataset

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    tqdm = None
    HAS_TQDM = False

# ──────────────────────────────────────────────────────────────────────────────
# Shared imports from adversarial_evaluation.py
# ──────────────────────────────────────────────────────────────────────────────
from adversarial_evaluation import (
    FileEntry,
    TextSample,
    balanced_limit_samples,
    build_file_entries,
    choose_threshold_at_target_fpr,
    collect_text_samples,
    evaluate_threshold,
    labels_from_samples,
    plot_roc,
    run_engineered_evaluation,
    split_entries_by_group,
    write_scores_csv,
)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — TS-CNN (adversary-side baseline)
# ══════════════════════════════════════════════════════════════════════════════

class _TSCNNDataset(Dataset):
    def __init__(self, samples: Sequence[TextSample], tokenizer, max_length: int):
        self.samples = list(samples)
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx: int):
        sample = self.samples[idx]
        enc = self.tokenizer(
            sample.text,
            truncation=True,
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt",
        )
        return {
            "input_ids": enc["input_ids"].squeeze(0),
            "label": torch.tensor(sample.label, dtype=torch.long),
        }


class _TSCNNModel(nn.Module):
    """
    Text steganalysis CNN (Yang et al., 2020 – TS-CSW).
    Multi-scale convolutional filters over token embeddings,
    global max-pool, then fully-connected classification head.
    """

    def __init__(
        self,
        vocab_size: int,
        embed_dim: int = 128,
        num_filters: int = 64,
        kernel_sizes: Sequence[int] = (1, 2, 3, 4),
        dropout: float = 0.5,
    ):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.convs = nn.ModuleList(
            [nn.Conv1d(embed_dim, num_filters, k) for k in kernel_sizes]
        )
        concat_dim = num_filters * len(kernel_sizes)
        self.fc1 = nn.Linear(concat_dim, 128)
        self.fc2 = nn.Linear(128, 2)
        self.drop = nn.Dropout(dropout)

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        x = self.embedding(input_ids)          # (B, L, E)
        x = x.transpose(1, 2)                  # (B, E, L) for Conv1d
        pooled = []
        for conv in self.convs:
            c = F.relu(conv(x))                # (B, F, L-k+1)
            p = c.max(dim=2).values            # (B, F)
            pooled.append(p)
        x = torch.cat(pooled, dim=1)           # (B, 4*F)
        x = self.drop(F.relu(self.fc1(x)))
        return self.fc2(x)                     # (B, 2)


class TSCNNClassifier:
    """Sklearn-style wrapper around the TS-CNN model."""

    def __init__(
        self,
        max_length: int = 128,
        embed_dim: int = 128,
        num_filters: int = 64,
        kernel_sizes: Sequence[int] = (1, 2, 3, 4),
        epochs: int = 5,
        batch_size: int = 32,
        lr: float = 1e-3,
        device: Optional[str] = None,
    ):
        self.max_length = max_length
        self.embed_dim = embed_dim
        self.num_filters = num_filters
        self.kernel_sizes = kernel_sizes
        self.epochs = epochs
        self.batch_size = batch_size
        self.lr = lr
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model: Optional[_TSCNNModel] = None
        self.tokenizer = None

    def _get_tokenizer(self):
        if self.tokenizer is None:
            from transformers import BertTokenizer
            self.tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")
        return self.tokenizer

    def train(
        self,
        train_samples: Sequence[TextSample],
        val_samples: Sequence[TextSample],
    ) -> None:
        tok = self._get_tokenizer()
        vocab_size = tok.vocab_size

        self.model = _TSCNNModel(
            vocab_size=vocab_size,
            embed_dim=self.embed_dim,
            num_filters=self.num_filters,
            kernel_sizes=self.kernel_sizes,
        ).to(self.device)

        train_ds = _TSCNNDataset(train_samples, tok, self.max_length)
        val_ds = _TSCNNDataset(val_samples, tok, self.max_length)
        train_loader = DataLoader(train_ds, batch_size=self.batch_size, shuffle=True)
        val_loader = DataLoader(val_ds, batch_size=self.batch_size)

        optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        criterion = nn.CrossEntropyLoss()

        for epoch in range(self.epochs):
            self.model.train()
            total_loss = 0.0
            it = train_loader
            if HAS_TQDM:
                it = tqdm(train_loader, desc=f"TS-CNN epoch {epoch+1}/{self.epochs}")
            for batch in it:
                ids = batch["input_ids"].to(self.device)
                labels = batch["label"].to(self.device)
                optimizer.zero_grad()
                logits = self.model(ids)
                loss = criterion(logits, labels)
                loss.backward()
                optimizer.step()
                total_loss += float(loss.item())

            val_acc = self._accuracy(val_loader)
            mean_loss = total_loss / max(1, len(train_loader))
            print(f"  Epoch {epoch+1}: loss={mean_loss:.4f}, val_acc={val_acc:.4f}")

    def _accuracy(self, loader: DataLoader) -> float:
        assert self.model is not None
        self.model.eval()
        correct = total = 0
        with torch.no_grad():
            for batch in loader:
                ids = batch["input_ids"].to(self.device)
                labels = batch["label"].to(self.device)
                preds = self.model(ids).argmax(dim=-1)
                correct += int((preds == labels).sum().item())
                total += int(len(labels))
        return correct / total if total else 0.0

    def predict_proba(self, samples: Sequence[TextSample]) -> np.ndarray:
        assert self.model is not None
        tok = self._get_tokenizer()
        ds = _TSCNNDataset(samples, tok, self.max_length)
        loader = DataLoader(ds, batch_size=self.batch_size)
        self.model.eval()
        probs: List[float] = []
        with torch.no_grad():
            for batch in loader:
                ids = batch["input_ids"].to(self.device)
                p = F.softmax(self.model(ids), dim=-1)[:, 1].cpu().numpy()
                probs.extend(p.tolist())
        return np.array(probs, dtype=float)


def run_tscnn_evaluation(args: Namespace) -> Dict[str, Any]:
    """Run TS-CNN steganalysis baseline and return results dict."""
    print("\n=== TS-CNN Adversary Baseline ===")
    print(f"Benign dir : {args.benign_dir}")
    print(f"Covert dir : {args.covert_dir}")
    print(f"Target FPR : {args.target_fpr}")
    print(f"Output dir : {args.output_dir}\n")

    entries = build_file_entries(args.benign_dir, args.covert_dir, args.group_key)
    trainval_entries, test_entries = split_entries_by_group(
        entries, args.test_size, args.seed, "train/test"
    )
    fit_entries, val_entries = split_entries_by_group(
        trainval_entries, args.validation_size, args.seed + 17, "fit/validation"
    )

    fit_samples = collect_text_samples(fit_entries)
    val_samples = collect_text_samples(val_entries)
    test_samples = collect_text_samples(test_entries)

    fit_samples = balanced_limit_samples(fit_samples, args.max_samples, args.seed)
    val_samples = balanced_limit_samples(val_samples, max(50, args.max_samples // 5), args.seed + 1)
    test_samples = balanced_limit_samples(test_samples, max(50, args.max_samples // 5), args.seed + 2)

    if not fit_samples or not val_samples or not test_samples:
        raise ValueError("Text extraction produced empty split(s)")

    y_fit = labels_from_samples(fit_samples)
    y_val = labels_from_samples(val_samples)
    y_test = labels_from_samples(test_samples)

    for name, y in [("fit", y_fit), ("val", y_val), ("test", y_test)]:
        if len(set(y)) < 2:
            raise ValueError(f"TS-CNN {name} split must contain both classes")

    print(f"Fit samples : {len(fit_samples)}")
    print(f"Val samples : {len(val_samples)}")
    print(f"Test samples: {len(test_samples)}")

    clf = TSCNNClassifier(
        max_length=args.tscnn_max_length,
        embed_dim=args.tscnn_embed_dim,
        num_filters=args.tscnn_num_filters,
        epochs=args.tscnn_epochs,
        batch_size=args.tscnn_batch_size,
    )
    clf.train(fit_samples, val_samples)

    val_scores = clf.predict_proba(val_samples)
    threshold, val_fpr, val_tpr = choose_threshold_at_target_fpr(y_val, val_scores, args.target_fpr)

    test_scores = clf.predict_proba(test_samples)
    fpr_curve, tpr_curve, _ = roc_curve(y_test, test_scores)
    roc_auc = float(auc(fpr_curve, tpr_curve))
    metrics = evaluate_threshold(y_test, test_scores, threshold, args.epsilon_smoothing)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "mode": "ts_cnn",
        "classifier": "ts_cnn",
        "features": "semantic",
        "target_fpr": args.target_fpr,
        "validation_threshold": float(threshold),
        "validation_fpr": float(val_fpr),
        "validation_tpr": float(val_tpr),
        "actual_fpr": metrics["actual_fpr"],
        "tpr": metrics["tpr"],
        "epsilon": metrics["epsilon"],
        "roc_auc": roc_auc,
        "tp": metrics["tp"],
        "fp": metrics["fp"],
        "tn": metrics["tn"],
        "fn": metrics["fn"],
        "n_fit": int(len(y_fit)),
        "n_validation": int(len(y_val)),
        "n_test": int(len(y_test)),
        "epsilon_smoothing": args.epsilon_smoothing,
        "tscnn_embed_dim": args.tscnn_embed_dim,
        "tscnn_num_filters": args.tscnn_num_filters,
        "tscnn_epochs": args.tscnn_epochs,
        "tscnn_max_length": args.tscnn_max_length,
    }

    with open(out_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)

    with open(out_dir / "args.json", "w") as f:
        json.dump(vars(args), f, indent=2)

    split_manifest = {
        "fit_files": sorted({s.source_file for s in fit_samples}),
        "validation_files": sorted({s.source_file for s in val_samples}),
        "test_files": sorted({s.source_file for s in test_samples}),
    }
    with open(out_dir / "split_manifest.json", "w") as f:
        json.dump(split_manifest, f, indent=2)

    plot_roc(fpr_curve, tpr_curve, roc_auc, "TS-CNN semantic", out_dir / "roc_curve.png")
    write_scores_csv(out_dir / "validation_scores.csv", val_samples, y_val, val_scores)
    write_scores_csv(out_dir / "test_scores.csv", test_samples, y_test, test_scores)

    print("\n=== TS-CNN Results ===")
    print(f"Validation FPR : {val_fpr:.4f}")
    print(f"Validation TPR : {val_tpr:.4f}")
    print(f"Test FPR       : {metrics['actual_fpr']:.4f}")
    print(f"Test TPR       : {metrics['tpr']:.4f}")
    print(f"Empirical ε    : {metrics['epsilon']:.4f}")
    print(f"ROC AUC        : {roc_auc:.4f}")
    print(f"Results saved  : {out_dir}")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — NLS Huffman encoder (covert-side baseline)
# ══════════════════════════════════════════════════════════════════════════════

@total_ordering
class _HeapNode:
    __slots__ = ("token", "freq", "left", "right")

    def __init__(self, token, freq):
        self.token = token
        self.freq = freq
        self.left = None
        self.right = None

    def __lt__(self, other):
        return self.freq < other.freq

    def __eq__(self, other):
        if not isinstance(other, _HeapNode):
            return False
        return self.freq == other.freq


class _HuffmanCoding:
    def __init__(self):
        self.heap: list = []
        self.codes: Dict[int, str] = {}

    def make_heap_from_array(self, freqs):
        for i, f in enumerate(freqs):
            heapq.heappush(self.heap, _HeapNode(i, float(f)))

    def merge_nodes(self):
        while len(self.heap) > 1:
            n1 = heapq.heappop(self.heap)
            n2 = heapq.heappop(self.heap)
            merged = _HeapNode(None, n1.freq + n2.freq)
            merged.left = n1
            merged.right = n2
            heapq.heappush(self.heap, merged)

    def _build_codes(self, node, code: str):
        if node is None:
            return
        if node.token is not None:
            self.codes[node.token] = code
            return
        self._build_codes(node.left, code + "0")
        self._build_codes(node.right, code + "1")

    def make_codes(self) -> _HeapNode:
        root = heapq.heappop(self.heap)
        self._build_codes(root, "")
        return root


class NLSHuffmanEncoder:
    """
    NLS Huffman-over-GPT2 encoder.
    Encodes a bitstring into text by greedily selecting tokens from
    the top-2^bpw LM candidates using a Huffman tree.

    This is the encoder-side of: Fang et al., "Encoded Prior Matching
    for Fast and Secure Linguistic Steganography" (ACL 2022) and the
    baseline used in zero-shot-GLS prior_works/NLS.
    """

    def __init__(self, model_name: str = "gpt2", device: str = "cpu", bits_per_word: int = 3):
        from transformers import GPT2LMHeadModel, GPT2Tokenizer
        print(f"[NLS] Loading {model_name} ...", flush=True)
        self.tokenizer = GPT2Tokenizer.from_pretrained(model_name)
        self.model = GPT2LMHeadModel.from_pretrained(model_name).to(device)
        self.model.eval()
        self.device = device
        self.bpw = bits_per_word

    @torch.no_grad()
    def _encode_chunk(self, bits: List[int], max_tokens: int = 40) -> Tuple[str, int]:
        """Encode bits into text. Returns (text, bits_consumed)."""
        bos = self.tokenizer.bos_token_id or self.tokenizer.eos_token_id or 0
        output_ids = torch.tensor([bos], dtype=torch.long, device=self.device)

        i = 0
        for _ in range(max_tokens):
            if i >= len(bits):
                break
            logits = self.model(output_ids.unsqueeze(0)).logits[0, -1, :]
            logits[-1] = -1e10  # block <|endoftext|>

            top_k = 2 ** self.bpw
            top_logits, top_indices = logits.topk(top_k)
            probs = F.softmax(top_logits, dim=-1).cpu().numpy()

            coding = _HuffmanCoding()
            coding.make_heap_from_array(probs)
            coding.merge_nodes()
            root = coding.make_codes()

            node = root
            while node.token is None:
                if i >= len(bits):
                    node = node.left
                else:
                    node = node.left if bits[i] == 0 else node.right
                    i += 1

            selected_id = top_indices[node.token].item()
            output_ids = torch.cat(
                [output_ids, torch.tensor([selected_id], dtype=torch.long, device=self.device)]
            )

        generated_ids = output_ids[1:].tolist()  # skip BOS
        text = self.tokenizer.decode(generated_ids, skip_special_tokens=True).replace("\n", " ").strip()
        return text, i

    def encode_to_chunks(self, num_chunks: int, seed: int = 42) -> List[str]:
        """
        Generate `num_chunks` stegotext chunks encoding random bits.
        The bits are random (as a proxy for an arbitrary secret) so
        the resulting text distribution reflects the encoder's output
        statistics without needing the original secrets.
        """
        rng = random.Random(seed)
        chunks = []
        for _ in range(num_chunks):
            n_bits = 40 * self.bpw  # enough bits for max_tokens=40
            bits = [rng.randint(0, 1) for _ in range(n_bits)]
            text, _ = self._encode_chunk(bits, max_tokens=40)
            chunks.append(text if text else "[nls-empty]")
        return chunks


def _count_semantic_events(trace_path: Path) -> int:
    """Count events with non-empty semantic_text in a JSONL trace file."""
    count = 0
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("semantic_text", "").strip():
                count += 1
    return count


def _rewrite_trace_with_nls(
    src_path: Path,
    dst_path: Path,
    nls_chunks: List[str],
) -> None:
    """
    Copy a JSONL trace, replacing semantic_text in sender events with
    pre-generated NLS chunks. Preserves all other fields exactly.
    """
    chunk_iter = iter(nls_chunks)
    lines_out = []
    with open(src_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                lines_out.append(line)
                continue
            try:
                obj = json.loads(stripped)
            except Exception:
                lines_out.append(line)
                continue
            if isinstance(obj, dict) and obj.get("semantic_text", "").strip():
                chunk = next(chunk_iter, "[nls-empty]")
                obj["semantic_text"] = chunk
                obj["semantic_content_type"] = "NLS_HuffmanGPT2"
                obj["semantic_label"] = "nls_baseline_payload"
            lines_out.append(json.dumps(obj) + "\n")

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dst_path, "w", encoding="utf-8") as f:
        f.writelines(lines_out)


def generate_nls_covert_traces(
    covert_dir: str,
    output_dir: str,
    model_name: str = "gpt2",
    bits_per_word: int = 3,
    max_files: Optional[int] = None,
    seed: int = 42,
) -> Path:
    """
    Swap semantic_text in existing covert traces with NLS Huffman text.
    Routing / behavioral structure is preserved unchanged.
    Returns path to the output directory.
    """
    src_dir = Path(covert_dir)
    dst_dir = Path(output_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    trace_files = sorted(src_dir.glob("*.jsonl"))
    if max_files:
        trace_files = trace_files[:max_files]

    if not trace_files:
        raise ValueError(f"No JSONL files found in {src_dir}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    encoder = NLSHuffmanEncoder(model_name=model_name, device=device, bits_per_word=bits_per_word)

    it = trace_files
    if HAS_TQDM:
        it = tqdm(trace_files, desc="NLS trace rewrite")

    for i, src_path in enumerate(it):
        n_events = _count_semantic_events(src_path)
        if n_events == 0:
            # No semantic events; copy as-is (receiver-side or empty)
            import shutil
            shutil.copy2(src_path, dst_dir / src_path.name)
            continue

        nls_chunks = encoder.encode_to_chunks(n_events, seed=seed + i)
        dst_path = dst_dir / src_path.name
        _rewrite_trace_with_nls(src_path, dst_path, nls_chunks)

    print(f"[NLS] Wrote {len(trace_files)} trace files to {dst_dir}")
    return dst_dir


def run_covert_baseline(args: Namespace) -> None:
    """Generate NLS covert traces then run adversarial evaluation."""
    out_root = Path(args.output_dir)
    nls_covert_dir = out_root / "nls_sender"

    print("\n=== Covert Encoder Baseline (NLS / Huffman-GPT2) ===")
    print(f"Source covert  : {args.covert_dir}")
    print(f"Benign dir     : {args.benign_dir}")
    print(f"NLS output dir : {nls_covert_dir}")
    print(f"GPT-2 bpw      : {args.bits_per_word}")
    print(f"Smoke test     : {args.smoke}\n")

    max_files = 20 if args.smoke else None
    generate_nls_covert_traces(
        covert_dir=args.covert_dir,
        output_dir=str(nls_covert_dir),
        model_name=args.gpt2_model,
        bits_per_word=args.bits_per_word,
        max_files=max_files,
        seed=args.seed,
    )

    # Run adversarial evaluation on NLS traces
    eval_args = Namespace(
        features="cross",
        classifier="rf",
        bert_context=False,
        benign_dir=args.benign_dir,
        covert_dir=str(nls_covert_dir),
        target_fpr=args.target_fpr,
        test_size=args.test_size,
        validation_size=args.validation_size,
        seed=args.seed,
        output_dir=str(out_root / "nls_eval_cross_rf"),
        manifest_path=args.manifest,
        workers=args.workers,
        no_progress=args.no_progress,
        max_samples=1000,
        bert_epochs=3,
        bert_batch_size=16,
        bert_max_length=128,
        user_key=args.user_key,
        group_key=args.group_key,
        epsilon_smoothing=args.epsilon_smoothing,
    )

    print("\n--- Adversarial eval on NLS traces (cross + RF) ---")
    try:
        results = run_engineered_evaluation(eval_args)
        eps = results.get("epsilon", float("nan"))
        print(f"\n[NLS] Epsilon (cross+RF) = {eps:.4f}")
        print("[NLS] Compare with our system's epsilon from adversarial_evaluation.py")
        print("[NLS] Lower epsilon = harder to detect = better for covert side")

        summary = {
            "baseline": "NLS_HuffmanGPT2",
            "note": "Swap covert encoder; routing/behavioral structure is identical to our system",
            "epsilon": eps,
            "roc_auc": results.get("roc_auc", float("nan")),
            "actual_fpr": results.get("actual_fpr", float("nan")),
            "tpr": results.get("tpr", float("nan")),
            "features": "cross",
            "classifier": "rf",
        }
        with open(out_root / "covert_baseline_summary.json", "w") as f:
            json.dump(summary, f, indent=2)
        print(f"Summary saved : {out_root / 'covert_baseline_summary.json'}")
    except Exception as e:
        print(f"[ERROR] Eval failed: {e}")
        raise


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Argument parsing and main
# ══════════════════════════════════════════════════════════════════════════════

def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--benign-dir", required=True,
                   help="Directory with benign JSONL traces")
    p.add_argument("--covert-dir", required=True,
                   help="Directory with covert JSONL traces")
    p.add_argument("--output-dir", default="baseline_results",
                   help="Root output directory")
    p.add_argument("--target-fpr", type=float, default=0.05)
    p.add_argument("--test-size", type=float, default=0.3)
    p.add_argument("--validation-size", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--workers", type=int, default=max(1, os.cpu_count() or 1))
    p.add_argument("--no-progress", action="store_true")
    p.add_argument("--user-key", default="role")
    p.add_argument("--group-key", default="user_key")
    p.add_argument("--epsilon-smoothing", type=float, default=1e-6)
    p.add_argument("--manifest", default="experiments/experiment_manifest.json")
    p.add_argument("--smoke", action="store_true",
                   help="Smoke test: limit data and epochs for a quick sanity check")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DeployStega baseline evaluations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── adversary ──────────────────────────────────────────────────────────
    adv = sub.add_parser("adversary", help="TS-CNN adversary-side baseline")
    _add_common_args(adv)
    adv.add_argument("--max-samples", type=int, default=10000)
    adv.add_argument("--tscnn-epochs", type=int, default=5)
    adv.add_argument("--tscnn-batch-size", type=int, default=32)
    adv.add_argument("--tscnn-max-length", type=int, default=128)
    adv.add_argument("--tscnn-embed-dim", type=int, default=128)
    adv.add_argument("--tscnn-num-filters", type=int, default=64)

    # ── covert ────────────────────────────────────────────────────────────
    cov = sub.add_parser("covert", help="NLS/Huffman covert encoder baseline")
    _add_common_args(cov)
    cov.add_argument("--gpt2-model", default="gpt2",
                     help="GPT-2 model name (gpt2 or gpt2-medium if available)")
    cov.add_argument("--bits-per-word", type=int, default=3,
                     help="Bits embedded per token (2 or 3)")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.smoke:
        print("[SMOKE] Smoke-test mode: reducing epochs and sample limits")
        if args.command == "adversary":
            args.max_samples = 200
            args.tscnn_epochs = 2

    if args.command == "adversary":
        run_tscnn_evaluation(args)
    elif args.command == "covert":
        run_covert_baseline(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
