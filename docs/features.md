# DeployStega Feature Set Specification

This document formally defines the adversarial **feature space** $\mathcal{F}$ used in the
DeployStega framework.

- **Features** are **measurable quantities extracted from logs** and used as **inputs** to adversarial classifiers.
- **Metrics** are **evaluation outputs** (e.g., classifier AUC, empirical $\varepsilon$) that quantify how well an adversary can detect covert behavior **using** features.

This document enumerates **features only**.

---

## Notation

### Logs and structure
We model platform activity as event logs.

- A **user log** is a time-ordered sequence of events for one user:
  $$\ell_u = (e_1, e_2, \dots, e_n)$$

- Each **event** $e$ has at least:
  - timestamp $t(e)$
  - action/event type $\text{type}(e)$
  - artifact identity $\text{id}(e)$ (e.g., `(artifact_class, *identifier)`)
  - role $\text{role}(e)\in\{\text{sender},\text{receiver}\}$ (when available)
  - optional text content $\text{text}(e)$ (for message-generating events)

### Windows
We define fixed, adversary-known segmentation functions:

- **Message window**: individual message-bearing event(s) (e.g., a comment body).
- **Session window**: contiguous block of events for user $u$ separated by inactivity gaps:
  $$\text{session}(u) = \{e_i,\dots,e_j\}$$
  (gap threshold is fixed and public to the adversary).
- **Epoch window**: platform-defined epoch index $\text{epoch}(e)\in\mathbb{Z}_{\ge 0}$.
- **User window**: all events for a user $u$ over the evaluation horizon.
- **Pair window**: all events for a sender–receiver pair $(s,r)$ over the horizon.

A feature is extracted by applying a function to a window:
$$f(W) \in \mathbb{R}^d$$

---

## What “aggregation” means (explicit, not vague)

Many features are naturally computed at a **base window**, then summarized at larger windows.

Example:
- Base: compute **per-message** perplexity values $x_1,x_2,\dots,x_m$ inside a session.
- Per-session aggregation then produces:
  - `mean`: $\frac{1}{m}\sum_i x_i$
  - `variance`: $\frac{1}{m}\sum_i (x_i-\bar{x})^2$
  - `quantiles`: e.g., $q_{0.5}, q_{0.9}$
  - `histogram`: counts in fixed bins

So “mean/variance under per-session” **does not mean** “mean of a session.”
It means: **mean of the base feature values that occurred inside that session**.

---

## Capability Class

The adversary’s capability class is:

$$
\mathcal{F} =
\mathcal{F}_{\text{semantic}}
\;\cup\;
\mathcal{F}_{\text{behavioral}}
\;\cup\;
\mathcal{F}_{\text{routing}}
$$

---

# 1) Semantic Feature Space $\mathcal{F}_{\text{semantic}}$

Semantic features are computed from user-generated text in message-bearing events
(e.g., issue bodies, comments, PR descriptions).

### Semantic features (definitions)

| Feature Name | Symbol | Definition (base computation) |
|---|---|---|
| Perplexity | $f_{\text{ppl}}$ | Per-message perplexity under a reference LM on the message text |
| Token-level KL divergence | $f_{\text{KL}}$ | KL divergence between next-token distributions under two contexts (e.g., $C_0$ vs $C_1$) |
| Sentence embedding vector | $f_{\text{emb}}$ | Normalized embedding vector (e.g., SBERT) for the message text |
| Embedding distance | $f_{\text{emb-dist}}$ | Pairwise cosine distance between embeddings of messages within a window |
| Token count | $f_{\text{len}}$ | Number of tokens (under fixed tokenizer) in the message text |

---

## Allowed aggregation windows (Semantic)

**IMPORTANT:** This table uses **words only** (no checkmarks).
Each cell explicitly says what is computed at that window.

**Cell semantics**
- `raw` = the feature is computed directly at that window (base output)
- `agg(...)` = compute per-base values inside the window, then summarize using the listed operators
- `—` = not defined / not used at that window

| Feature (Symbol) | Per-Message | Per-Session | Per-Epoch | Per-User |
|---|---|---|---|---|
| $f_{\text{ppl}}$ | raw | agg(mean, variance, quantiles) | agg(mean, variance, quantiles) | agg(mean, variance, quantiles) |
| $f_{\text{KL}}$ | raw | agg(mean, quantiles) | agg(mean, quantiles) | agg(mean, quantiles) |
| $f_{\text{emb}}$ | raw (vector) | — | — | — |
| $f_{\text{emb-dist}}$ | raw (pairwise, within window) | agg(histogram, mean, quantiles) | agg(histogram, mean, quantiles) | agg(histogram, mean, quantiles) |
| $f_{\text{len}}$ | raw | agg(mean, variance, quantiles) | agg(mean, variance, quantiles) | agg(mean, variance, quantiles) |

**Notes**
- We do **not** aggregate $f_{\text{emb}}$ here because it is a high-dimensional vector; keeping it raw avoids conflating representation with summary statistics. If you later want it, define an explicit operator set (e.g., PCA projection + mean) and add it here.

---

# 2) Behavioral Feature Space $\mathcal{F}_{\text{behavioral}}$

Behavioral features capture timing and interaction structure from logs, independent of text meaning.

### Behavioral features (definitions)

| Feature Name | Symbol | Definition (base computation) |
|---|---|---|
| Inter-event time | $f_t$ | $\Delta t_i = t(e_{i}) - t(e_{i-1})$ for consecutive events by same user |
| Session length | $f_{\text{sess}}$ | session duration: $t(e_{\text{last}}) - t(e_{\text{first}})$ |
| Action frequency | $f_{\text{freq}}$ | count of events per fixed time unit (e.g., per hour, per day) |
| Event-type frequency | $f_{\text{etype}}$ | normalized distribution over event types within window |
| Artifact revisit rate | $f_{\text{revisit}}$ | fraction of events whose artifact id was seen before in the window |
| Artifact transition topology | $f_{\text{trans}}$ | transition matrix / probabilities over artifact classes (or artifact IDs) |
| Sender→receiver latency | $f_{\text{review-lat}}$ | time between sender write/update and receiver reply (when defined) |
| Retrieval latency | $f_{\text{retr-lat}}$ | time from sender update to receiver access of updated artifact state |
| Temporal correlation | $f_{\text{corr}}$ | cross-correlation / coupling statistic between sender and receiver activity series |

---

## Allowed aggregation windows (Behavioral)

Again: **words only**, and each cell spells out what is computed.

| Feature (Symbol) | Per-Event | Per-Session | Per-Epoch | Per-User | Per-Pair |
|---|---|---|---|---|---|
| $f_t$ | raw | agg(histogram, mean, quantiles) | agg(histogram, mean, quantiles) | agg(histogram, mean, quantiles) | — |
| $f_{\text{sess}}$ | — | raw | agg(histogram, mean, quantiles) | agg(histogram, mean, quantiles) | — |
| $f_{\text{freq}}$ | — | raw (events / unit) | raw (events / unit) | agg(mean, variance, quantiles) | — |
| $f_{\text{etype}}$ | raw (one-hot type) | agg(mean-as-proportions) | agg(mean-as-proportions) | agg(mean-as-proportions) | — |
| $f_{\text{revisit}}$ | raw | agg(mean, quantiles) | agg(mean, quantiles) | agg(mean, quantiles) | — |
| $f_{\text{trans}}$ | raw (transition step) | agg(mean-as-transition-probs) | agg(mean-as-transition-probs) | agg(mean-as-transition-probs) | — |
| $f_{\text{review-lat}}$ | raw | agg(histogram, mean, quantiles) | agg(histogram, mean, quantiles) | agg(histogram, mean, quantiles) | agg(histogram, mean, quantiles) |
| $f_{\text{retr-lat}}$ | raw | agg(histogram, mean, quantiles) | agg(histogram, mean, quantiles) | agg(histogram, mean, quantiles) | agg(histogram, mean, quantiles) |
| $f_{\text{corr}}$ | — | raw (pair time series) | agg(mean, quantiles) | agg(mean, quantiles) | raw |

**Clarification about “mean-as-proportions”**
- For distributions (event-type freq, transitions), the base outputs are vectors summing to 1. “mean-as-proportions” means elementwise averaging of those vectors.

---

# 3) Routing Feature Space $\mathcal{F}_{\text{routing}}$

Routing features focus on **artifact identity** and **multi-role overlap** induced by dead-drop routing.

### Routing features (definitions)

| Feature Name | Symbol | Definition |
|---|---|---|
| Identifier concentration (HHI) | $f_{\text{HHI}}$ | $\sum_i p_i^2$ over artifact IDs accessed in a window |
| Identifier normalized entropy | $f_{\text{entropy}}$ | $H(p)/\log(|\text{support}(p)|)$ in $[0,1]$ |
| Role asymmetry over artifact classes | $f_{\text{role-dist}}$ | divergence between sender vs receiver distributions over artifact_class |
| Shared artifact overlap | $f_{\text{overlap}}$ | fraction of artifact IDs touched by both roles at least once |
| Sender-only fraction | $f_{\text{sender-only}}$ | fraction of IDs touched only by sender |
| Receiver-only fraction | $f_{\text{receiver-only}}$ | fraction of IDs touched only by receiver |
| Shared access topologytology vector | $f_{\text{topo}}$ | vector $(\text{both}, \text{sender-only}, \text{receiver-only})$ proportions |

---

## Allowed aggregation windows (Routing)

Routing is fundamentally identity-based and typically defined at epoch/user/pair scales.

| Feature (Symbol) | Per-Event | Per-Epoch | Per-User | Per-Pair |
|---|---|---|---|---|
| $f_{\text{HHI}}$ | — | raw | agg(mean, quantiles) | raw |
| $f_{\text{entropy}}$ | — | raw | agg(mean, quantiles) | raw |
| $f_{\text{role-dist}}$ | — | raw | raw | raw |
| $f_{\text{overlap}}$ | — | raw | — | raw |
| $f_{\text{sender-only}}$ | — | raw | — | raw |
| $f_{\text{receiver-only}}$ | — | raw | — | raw |
| $f_{\text{topo}}$ | — | raw (vector) | — | raw (vector) |

---

## Summary: Features vs Metrics (one sentence each)

- **Features** ($\mathcal{F}$): measurable log-derived quantities used as classifier inputs.
- **Metrics** (e.g., AUC, empirical $\varepsilon$): numbers summarizing an adversary’s ability to distinguish $D$ vs $D'$ **using** features.

---

## Role in Evaluation (context only)

These features form the complete adversarial observable space supplied to adversarial classifiers.
Classifier performance (AUC, empirical $\varepsilon$, etc.) is reported elsewhere as **evaluation metrics**.
