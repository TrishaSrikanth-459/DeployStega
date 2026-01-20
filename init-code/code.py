import json
import math
import random
from dataclasses import dataclass
from typing import List, Dict, Tuple

import numpy as np
import pandas as pd
import torch
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModelForCausalLM
from sentence_transformers import SentenceTransformer

class Config:
    input_path: str = "data/benign.jsonl"
    out_features: str = "out/features.parquet"
    out_pairs: str = "out/pairs.parquet"
    lm_name: str = "gpt2"
    emb_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    # I got the following constants from chat
    max_chars: int = 8000           
    ppl_max_tokens: int = 512
    kl_prefix_tokens: int = 32      
    batch_size_lm: int = 8
    batch_size_emb: int = 64
    pair_samples_per_type: int = 100000
    seed: int = 42
    device: str = "cuda" if torch.cuda.is_available() else "cpu"


def load_jsonl(path: str, max_chars: int) -> pd.DataFrame:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            text = (obj["text"] or "").replace("\x00", "").strip()
            if not text:
                continue
            if len(text) > max_chars:
                text = text[:max_chars]
            rows.append({"id": obj["id"], "type": obj["type"], "text": text})
    df = pd.DataFrame(rows).drop_duplicates(subset=["id"])
    df["type"] = df["type"].astype(str)
    return df


def compute_ppl(df: pd.DataFrame, cfg: Config) -> Tuple[np.ndarray, np.ndarray]:
    tok = AutoTokenizer.from_pretrained(cfg.lm_name)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    lm = AutoModelForCausalLM.from_pretrained(cfg.lm_name).to(cfg.device)
    lm.eval()

    ppls = np.zeros(len(df), dtype=np.float64)
    ntoks = np.zeros(len(df), dtype=np.int32)

    with torch.no_grad():
        for start in tqdm(range(0, len(df), cfg.batch_size_lm), desc="PPL"):
            batch = df.iloc[start:start + cfg.batch_size_lm]["text"].tolist()
            enc = tok(
                batch,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=cfg.ppl_max_tokens,
            )
            input_ids = enc["input_ids"].to(cfg.device)
            attn = enc["attention_mask"].to(cfg.device)
            out = lm(input_ids=input_ids, attention_mask=attn)
            logits = out.logits  
            shift_logits = logits[:, :-1, :]
            shift_labels = input_ids[:, 1:]
            shift_attn = attn[:, 1:]
            log_probs = torch.log_softmax(shift_logits, dim=-1)
            tgt_logp = log_probs.gather(-1, shift_labels.unsqueeze(-1)).squeeze(-1)
            tgt_logp = tgt_logp * shift_attn
            token_counts = shift_attn.sum(dim=1).clamp(min=1)
            nll = (-tgt_logp.sum(dim=1) / token_counts)  
            ppl = torch.exp(nll)
            ppls[start:start + len(batch)] = ppl.detach().cpu().numpy()
            ntoks[start:start + len(batch)] = token_counts.detach().cpu().numpy().astype(np.int32)
    return ppls, ntoks


def next_token_dist(lm, tok, texts: List[str], prefix_tokens: int, context: str, device: str) -> torch.Tensor:
    combined = []
    for t in texts:
        combined.append(context + t)
    enc = tok(combined, return_tensors="pt", padding=True, truncation=True,max_length=prefix_tokens + 64)
    input_ids = enc["input_ids"].to(device)
    attn = enc["attention_mask"].to(device)
    with torch.no_grad():
        out = lm(input_ids=input_ids, attention_mask=attn)
        logits = out.logits
    last_idx = attn.sum(dim=1) - 1 
    batch_indices = torch.arange(input_ids.size(0), device=device)
    last_logits = logits[batch_indices, last_idx, :]
    probs = torch.softmax(last_logits, dim=-1)
    return probs


def compute_kl(df: pd.DataFrame, cfg: Config) -> np.ndarray:
    tok = AutoTokenizer.from_pretrained(cfg.lm_name)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    lm = AutoModelForCausalLM.from_pretrained(cfg.lm_name).to(cfg.device)
    lm.eval()
    C0 = ""
    C1 = "Text" # Text from github artifact
    kls = np.zeros(len(df), dtype=np.float64)
    eps = 1e-12
    with torch.no_grad():
        for start in tqdm(range(0, len(df), cfg.batch_size_lm), desc="KL"):
            batch = df.iloc[start:start + cfg.batch_size_lm]["text"].tolist()
            p0 = next_token_dist(lm, tok, batch, cfg.kl_prefix_tokens, C0, cfg.device)
            p1 = next_token_dist(lm, tok, batch, cfg.kl_prefix_tokens, C1, cfg.device)
            p0 = torch.clamp(p0, min=eps)
            p1 = torch.clamp(p1, min=eps)
            kl = (p0 * (p0.log() - p1.log())).sum(dim=1) 
            kls[start:start + len(batch)] = kl.detach().cpu().numpy()
    return kls


def compute_embeddings(df: pd.DataFrame, cfg: Config) -> np.ndarray:
    model = SentenceTransformer(cfg.emb_name, device=cfg.device)
    texts = df["text"].tolist()
    embs = model.encode(texts, batch_size=cfg.batch_size_emb, show_progress_bar=True,normalize_embeddings=True, )
    return np.asarray(embs, dtype=np.float32)


def sample_pair_distances(df: pd.DataFrame, embs: np.ndarray, cfg: Config) -> pd.DataFrame:
    rng = random.Random(cfg.seed)
    out_rows = []
    for t, sub in df.groupby("type"):
        idxs = sub.index.to_list()
        n = len(idxs)
        if n < 2:
            continue
        m = min(cfg.pair_samples_per_type, n * (n - 1) // 2)
        for _ in tqdm(range(m), desc=f"Pairs {t}"):
            i, j = rng.sample(idxs, 2)
            d = 1.0 - float(np.dot(embs[i], embs[j]))
            out_rows.append({"type": t, "id1": df.at[i, "id"],"id2": df.at[j, "id"],"cos_dist": d})
    return pd.DataFrame(out_rows)
