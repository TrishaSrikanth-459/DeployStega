from __future__ import annotations

import json
import os
import re
import math
import glob
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from collections import Counter
import warnings

warnings.filterwarnings("ignore")


@dataclass
class TokenBin:
    bin_id: int
    tokens: List[str]

    @property
    def capacity_bits(self):
        if len(self.tokens) <= 1:
            return 0
        return int(math.log2(len(self.tokens)))


class ByteLevelStegoDecoder:
    def __init__(self, bins_path: str = None):
        self.bins = []
        self.token_to_bin_and_index = {}
        self.bin_by_id = {}
        self.byte_bins = []
        self.large_bins = []

        if bins_path is None:
            bins_path = self._find_byte_bins_file()

        self.token_re = re.compile(r"[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*")
        self._load_byte_level_bins(bins_path)

    def _tokenize_for_matching(self, text: str) -> List[str]:
        return [t.lower() for t in self.token_re.findall(text)]

    def _normalize_token(self, token: str) -> str:
        token = token.strip().lower()
        return re.sub(r"[^a-z0-9._-]", "", token)

    def _find_byte_bins_file(self) -> str:
        print("Looking for byte-level token bins...")

        base_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(base_dir, "../../token_binning_data/bins_k16.json"),
            os.path.join(base_dir, "../../token_binning_data/bins_k32.json"),
            os.path.join(base_dir, "../../token_binning_data/bins_k64.json"),
            os.path.join(base_dir, "../../token_binning_data/byte_level_bins.json"),
            os.path.join(base_dir, "bins_k16.json"),
            os.path.join(base_dir, "bins_k32.json"),
        ]

        for candidate in candidates:
            if os.path.exists(candidate):
                print(f"Found: {candidate}")
                return candidate

        token_dir = os.path.join(base_dir, "../../token_binning_data")
        if os.path.exists(token_dir):
            json_files = glob.glob(os.path.join(token_dir, "*.json"))
            for file in json_files:
                print(f"Found: {file}")
                return file

        default = os.path.join(base_dir, "../../token_binning_data/bins_k16.json")
        print(f"No bins file found, will try: {default}")
        return default

    def _load_byte_level_bins(self, bins_path: str):
        print(f"Loading bins from {bins_path}...")

        if not os.path.exists(bins_path):
            raise RuntimeError(f"Cannot load bins from {bins_path}: file not found")

        with open(bins_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        bins_data = data["bins"] if "bins" in data else data

        for bin_id, tokens in enumerate(bins_data):
            if not isinstance(tokens, list):
                continue

            clean_tokens = []
            for token in tokens:
                if isinstance(token, str) and token.strip():
                    clean_token = self._normalize_token(token)
                    if clean_token:
                        clean_tokens.append(clean_token)

            if len(clean_tokens) < 2:
                continue

            bin_obj = TokenBin(bin_id=bin_id, tokens=clean_tokens)
            self.bins.append(bin_obj)
            self.bin_by_id[bin_id] = bin_obj

            if len(clean_tokens) >= 256:
                self.byte_bins.append(bin_obj)
            elif len(clean_tokens) >= 64:
                self.large_bins.append(bin_obj)

            for idx, token in enumerate(clean_tokens):
                self.token_to_bin_and_index[token] = (bin_id, idx)

        if not self.bins:
            raise RuntimeError(f"Cannot load bins from {bins_path}: no valid bins found")

    def decode_with_positions(self, chunks: List[str], positions_file: str) -> str:
        with open(positions_file, "r", encoding="utf-8") as f:
            positions_data = json.load(f)

        chunks_data = positions_data.get("chunks", [])
        all_decoded_bytes = bytearray()

        for chunk_text, chunk_data in zip(chunks, chunks_data):
            positions = chunk_data.get("positions", [])
            tokens = self._tokenize_for_matching(chunk_text)
            chunk_bytes = self._decode_chunk_bytes(tokens, positions)
            all_decoded_bytes.extend(chunk_bytes)

        try:
            return all_decoded_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return all_decoded_bytes.decode("utf-8", errors="ignore")

    def _position_matches_exactly(self, tokens: List[str], pos_info: Dict[str, Any]) -> Optional[bool]:
        target_word = pos_info.get("chosen_word", "")
        token_position = pos_info.get("token_position")

        if token_position is None:
            return None

        if not target_word:
            return False

        if token_position < 0 or token_position >= len(tokens):
            return False

        return tokens[token_position] == self._normalize_token(target_word)

    def _decode_chunk_bytes(self, tokens: List[str], positions: List[Dict]) -> bytearray:
        if not positions:
            return bytearray()

        has_byte_index = any(pos.get("byte_index") is not None for pos in positions)
        if not has_byte_index:
            return self._decode_chunk_bytes_sequential(tokens, positions)

        remaining_counts = Counter(tokens)
        consumed_positions = set()
        expected_indices: List[int] = []
        bytes_by_index: Dict[int, int] = {}
        nibbles_by_index: Dict[int, Dict[str, int]] = {}

        for pos_info in positions:
            target_word = pos_info.get("chosen_word", "")
            encoding_type = pos_info.get("encoding_type", "byte")
            bits = pos_info.get("bits", 8)
            byte_index = pos_info.get("byte_index")

            if not target_word:
                continue

            if byte_index is not None:
                expected_indices.append(byte_index)

            clean_target = self._normalize_token(target_word)
            exact_match = self._position_matches_exactly(tokens, pos_info)

            if exact_match is None:
                found = remaining_counts.get(clean_target, 0) > 0
                if found:
                    remaining_counts[clean_target] -= 1
            else:
                token_position = pos_info.get("token_position")
                found = bool(exact_match)
                if found and token_position in consumed_positions:
                    found = False
                if found:
                    consumed_positions.add(token_position)

            if not found:
                continue

            chosen_index = pos_info.get("chosen_index", pos_info.get("target_index", 0))

            if bits == 4:
                nibble = chosen_index & 0x0F
                if byte_index is not None:
                    entry = nibbles_by_index.setdefault(byte_index, {})
                    if encoding_type == "high_nibble":
                        entry["high"] = nibble
                    elif encoding_type == "low_nibble":
                        entry["low"] = nibble
                    else:
                        if "high" not in entry:
                            entry["high"] = nibble
                        else:
                            entry["low"] = nibble
            else:
                byte_val = chosen_index & 0xFF
                if byte_index is not None:
                    bytes_by_index.setdefault(byte_index, byte_val)

        decoded_bytes = bytearray()
        for idx in sorted(set(expected_indices)):
            if idx in bytes_by_index:
                decoded_bytes.append(bytes_by_index[idx])
                continue

            entry = nibbles_by_index.get(idx, {})
            if "high" not in entry or "low" not in entry:
                continue

            decoded_bytes.append(((entry["high"] & 0x0F) << 4) | (entry["low"] & 0x0F))

        return decoded_bytes

    def _decode_chunk_bytes_sequential(self, tokens: List[str], positions: List[Dict]) -> bytearray:
        decoded_bytes = bytearray()
        remaining_counts = Counter(tokens)
        consumed_positions = set()
        pending_high = None

        for pos_info in positions:
            target_word = pos_info.get("chosen_word", "")
            encoding_type = pos_info.get("encoding_type", "byte")
            bits = pos_info.get("bits", 8)

            if not target_word:
                continue

            clean_target = self._normalize_token(target_word)
            exact_match = self._position_matches_exactly(tokens, pos_info)

            if exact_match is None:
                found = remaining_counts.get(clean_target, 0) > 0
                if found:
                    remaining_counts[clean_target] -= 1
            else:
                token_position = pos_info.get("token_position")
                found = bool(exact_match)
                if found and token_position in consumed_positions:
                    found = False
                if found:
                    consumed_positions.add(token_position)

            if not found:
                continue

            chosen_index = pos_info.get("chosen_index", pos_info.get("target_index", 0))

            if bits == 4:
                nibble = chosen_index & 0x0F
                if encoding_type == "high_nibble":
                    pending_high = nibble
                elif encoding_type == "low_nibble":
                    if pending_high is None:
                        continue
                    decoded_bytes.append(((pending_high & 0x0F) << 4) | nibble)
                    pending_high = None
                else:
                    if pending_high is None:
                        pending_high = nibble
                    else:
                        decoded_bytes.append(((pending_high & 0x0F) << 4) | nibble)
                        pending_high = None
            else:
                decoded_bytes.append(chosen_index & 0xFF)

        return decoded_bytes

