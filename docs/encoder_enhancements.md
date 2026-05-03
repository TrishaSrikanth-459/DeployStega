# Stego Encoder Enhancements

Changes applied to `routing/semantic/stego_encoder.py` to attack the residual
semantic detectability gap that the `ablation_results_common_support` run
exposed (behavioral AUC ≈ 0.39, semantic AUC = 1.00 with 22 hand-crafted
features: PPL, KL, MiniLM cosine, char/token stats).

The encoder used to frame steganography as a constrained writing task
("produce text that contains these required words"). It now treats it as a
**mimicry task**: produce text whose perplexity, KL, and embedding-space
distribution sit closer to the conditional benign distribution for the
artifact, with the bits embedded as a side effect.

The decoder (`stego_decoder.py`) is untouched. All changes preserve its
contract: tokenization regex, `token_position` indexing, `chosen_word`
matching, `byte_index` / `encoding_type` / `bits` semantics. `_extract_byte_positions`
is still run on the final chunk text after every regeneration.

## What changed

| # | Change | Where |
|---|---|---|
| 1 | Per-chunk capacity dropped from 96-128 bits (≈24 forced tokens / chunk) to a configurable default of 32 bits / 8 choices | `_choose_chunking_params`, `DEFAULT_TARGET_BITS_PER_CHUNK`, `DEFAULT_MAX_CHOICES_PER_CHUNK` |
| 2 | Optional artifact-context conditioning (parent text, repo language, file paths, related identifiers, title) injected into the prompt | `_generate_byte_chunk`, `_build_byte_prompt` (new `context_block`) |
| 3 | Few-shot benign exemplars per artifact_class loaded from `benign_traces.jsonl`, sampled per chunk, embedded in the prompt as style references | `_load_benign_exemplars`, `_pick_exemplars`, `_build_byte_prompt` (new `exemplar_block`) |
| 4 | Surface-form sampling (short prose / medium prose / bullet list / inline-code-heavy / terse / fenced code block / casual no-period) replaces the hard-coded "3-5 sentences, no bullets, no fences, terminal period" template | `SURFACE_FORMS`, `_pick_surface_form`, `_build_byte_prompt`, `_normalize_text` |
| 5 | Per-chunk persona rotation (triager / reviewer / contributor / maintainer / ops / docs) varies the system prompt voice | `PERSONAS`, `_pick_persona`, `_call_model` system addendum |
| 6 | Per-chunk sampling parameter variation: `temperature ∈ [0.7, 1.05]`, `top_p ∈ [0.85, 0.97]` (deterministic per (message, chunk_idx)) | `SAMPLING_BAND`, `_sample_temperature`, `_call_model` |
| 7 | Fenced code blocks allowed when ≥3 of the chunk's required tokens are code-like (the prior `_build_byte_prompt` actively forbade them) | `_generate_byte_chunk`, `_build_byte_prompt` |
| 8 | LLM "naturalness" validator gate disabled by default — it had been the main monoculture driver, pulling every accepted chunk toward one polished-prose attractor. Set `enable_surface_validator=True` to restore. | `__init__(enable_surface_validator=False)`, `_generate_byte_chunk` |
| 9 | Adjacent-duplicate-token rejection relaxed (real GitHub notes occasionally have it; the gate was forcing extra retries without helping detectability) | `_generate_byte_chunk` (`has_dup` always False) |
| 10 | Retry budget reduced 6 → 4 (gentler retries reduce homogenization) | `_generate_byte_chunk` |
| 11 | Per-message + per-chunk RNG seeded from message hash so persona / surface-form / sampling choices are reproducible across reruns of the same message but vary across messages | `_chunk_seed`, `encode_message` (`message_seed`) |

## What did NOT change

- Bin file (`token_binning_data/bins_k16.json`) — out of scope.
- Bit-packing schema: `byte_index`, `encoding_type`, `bits`, `chosen_index`,
  `chosen_word`, `token_position`. The positions JSON is still produced by
  `_extract_byte_positions` on the final chunk text.
- The in-order requirement on required words — preserved so the existing
  decoder works without modification.
- `ByteLevelStegoDecoder` — not touched.

## Caller-visible API additions (all backward compatible)

`ByteLevelStegoEncoder.__init__` and `ByteLevelSemanticEncoder.__init__` now
accept these optional kwargs (defaults preserve current behavior of any
caller that does not pass them):

| Kwarg | Default | Purpose |
|---|---|---|
| `benign_exemplars_path` | `None` | Path to a JSONL with `{artifact_class, semantic_text}`. If `None`, the encoder also checks the `STEGO_BENIGN_EXEMPLARS_PATH` env var and a few candidate paths relative to the encoder file (e.g. `../../benign_traces.jsonl`). Few-shot is silently skipped if no corpus is found. |
| `target_bits_per_chunk` | `32` | Bits per chunk; lower = fewer forced tokens per chunk. |
| `max_choices_per_chunk` | `8` | Hard cap on choices per chunk. |
| `enable_surface_validator` | `False` | If `True`, restores the old LLM-based naturalness gate and 6-retry loop. |

`encode_message`'s `context` dict now reads the following optional keys (any
combination, in addition to the existing `artifact_class` and `action`):

```python
context = {
    "artifact_class": "Issue",          # existing, required
    "action": "edit",                    # existing, required
    # New optional keys (use any subset):
    "issue_title":         "Crash on startup when config missing",
    "parent_text":         "<issue body / PR description / parent comment>",
    "repo_owner":          "kubernetes",
    "repo_name":           "kubernetes",
    "repo_language":       "Go",
    "file_paths":          ["pkg/scheduler/core/generic_scheduler.go"],
    "related_identifiers": ["#12345", "abc123def"],
}
```

When provided, these are surfaced to the LLM in an `Artifact context` block
so the generated text is plausibly *about that artifact* rather than a
generic "software development" comment. This is the single biggest expected
mover for `pair_cos_*` and `pair_by_type[GitHubText].mean`.

## Recommended caller upgrade

Both `covert_trace_generator.py` (top-level) and
`DeployStega/scripts/generate_covert_traces.py` currently pass only
`{artifact_class, action}`. They already have access to `RepositorySnapshot`
artifact metadata and `DeadDropResolver` results. Forwarding any of the
optional keys above into `context` will activate the conditioning path
without further code changes.

## Why this should move the needle

Each of the 22 semantic features is targeted by at least one change:

- `ppl_max`, `ppl_std` — A1 (less density), A4 (varied surface form), A10
  (sampling variance)
- `kl_*` — A2 (context conditioning), A3 (few-shot exemplars)
- `pair_cos_*`, `pair_by_type[GitHubText].mean/std` — A2, A3, A5 (persona
  rotation), A4 (format variance)
- `mean_chars`, `std_chars`, `ntoks_*` — A1, A4 (terse / bullets / code
  blocks broaden the length distribution)



