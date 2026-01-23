# DeployStega Feature Set Specification

This document formally defines the adversarial feature space $\mathcal{F}$ used in the
DeployStega framework. Features represent all semantic, behavioral, and routing
observables realistically accessible to an adversary via application-level logs.

We distinguish **features**, which are inputs to adversarial classifiers, from
**metrics**, which quantify detection performance. This document enumerates
features only.

---

## Notation

Let:
- $D$ denote a dataset of benign user interaction logs
- $D'$ denote a dataset where one or more users are replaced with covert users
- $\ell \in D \cup D'$ denote a single user interaction log
- $F(\ell) \in \mathbb{R}^d$ denote the feature vector extracted from $\ell$

The adversary’s capability class is defined as:

$$
\mathcal{F} =
\mathcal{F}_{\text{semantic}}
\;\cup\;
\mathcal{F}_{\text{behavioral}}
\;\cup\;
\mathcal{F}_{\text{routing}}
$$

---

## Semantic Feature Space $\mathcal{F}_{\text{semantic}}$

Semantic features capture linguistic deviations introduced by steganographic
encoding. These features are extracted from user-generated text artifacts such as
issue bodies, comments, commit messages, and pull request descriptions.

### Semantic Features

| Feature Name | Symbol | Description |
|-------------|--------|-------------|
| Perplexity | $f_{\text{ppl}}$ | Token-level perplexity under a reference language model |
| Token-level KL divergence | $f_{\text{KL}}$ | KL divergence between next-token distributions under two contexts |
| Sentence embedding | $f_{\text{emb}}$ | Normalized sentence embedding (e.g., SBERT) |
| Embedding distance | $f_{\text{emb-dist}}$ | Cosine distance between sentence embeddings |
| Token count | $f_{\text{len}}$ | Number of tokens in a message |

### Allowed Aggregation Windows

| Feature | Per-Message | Per-Session | Per-User |
|-------|-------------|-------------|----------|
| $f_{\text{ppl}}$ | ✓ | Mean, quantiles | Mean, variance |
| $f_{\text{KL}}$ | ✓ | Mean | Mean |
| $f_{\text{emb}}$ | ✓ | — | — |
| $f_{\text{emb-dist}}$ | ✓ | Histogram | Histogram |
| $f_{\text{len}}$ | ✓ | Mean | Mean |

Semantic features are **never aggregated across users** and are not defined below
the message level.

---

## Behavioral Feature Space $\mathcal{F}_{\text{behavioral}}$

Behavioral features capture temporal and structural properties of user interaction
patterns observable through authentication logs, API access logs, and application
event logs.

### Timing and Session Features

| Feature Name | Symbol | Description |
|-------------|--------|-------------|
| Inter-event time | $f_t$ | Time gap between consecutive user actions |
| Session length | $f_{\text{sess}}$ | Duration of a user session |
| Action frequency | $f_{\text{freq}}$ | Actions per unit time (hour/day) |

### Interaction Structure Features

| Feature Name | Symbol | Description |
|-------------|--------|-------------|
| Event-type frequency | $f_{\text{etype}}$ | Distribution over action types |
| Artifact revisit rate | $f_{\text{revisit}}$ | Probability of re-accessing the same artifact |
| Artifact transition | $f_{\text{trans}}$ | Transition probabilities between artifact classes |

### Cross-User Timing Correlation

| Feature Name | Symbol | Description |
|-------------|--------|-------------|
| Sender→receiver latency | $f_{\text{review-lat}}$ | Time between sender update and receiver access |
| Retrieval latency | $f_{\text{retr-lat}}$ | Delay between artifact update and later access |
| Temporal correlation | $f_{\text{corr}}$ | Bi-directional timing correlation between users |

### Allowed Aggregation Windows

| Feature | Per-Action | Per-Session | Per-User |
|-------|------------|-------------|----------|
| $f_t$ | ✓ | Histogram | Histogram |
| $f_{\text{sess}}$ | — | ✓ | Mean, variance |
| $f_{\text{freq}}$ | — | ✓ | Mean |
| $f_{\text{etype}}$ | ✓ | Histogram | Histogram |
| $f_{\text{revisit}}$ | ✓ | Mean | Mean |
| $f_{\text{trans}}$ | ✓ | Transition matrix | Mean matrix |
| $f_{\text{review-lat}}$ | — | ✓ | Histogram |
| $f_{\text{retr-lat}}$ | — | ✓ | Histogram |
| $f_{\text{corr}}$ | — | ✓ | ✓ |

Behavioral features are **single-user** unless explicitly labeled as cross-user.

---

## Routing Feature Space $\mathcal{F}_{\text{routing}}$

Routing features capture how users traverse application artifacts and how sender
and receiver behaviors overlap at the artifact-identity level. These features are
inherently **multi-user** and arise uniquely from application-layer dead-drop
communication.

### Routing Features

| Feature Name | Symbol | Description |
|-------------|--------|-------------|
| Identifier concentration (HHI) | $f_{\text{HHI}}$ | Herfindahl–Hirschman Index over accessed artifact IDs |
| Identifier entropy | $f_{\text{entropy}}$ | Normalized entropy of artifact ID access distribution |
| Role artifact distribution | $f_{\text{role-dist}}$ | Divergence between sender and receiver artifact-class distributions |
| Shared artifact overlap | $f_{\text{overlap}}$ | Fraction of artifact IDs accessed by both roles |
| Sender-only fraction | $f_{\text{sender-only}}$ | Artifacts accessed exclusively by sender |
| Receiver-only fraction | $f_{\text{receiver-only}}$ | Artifacts accessed exclusively by receiver |
| Shared topology profile | $f_{\text{topo}}$ | Vector of shared vs exclusive access proportions |

### Allowed Aggregation Windows

| Feature | Per-Epoch | Per-User-Pair | Per-Dataset |
|-------|-----------|---------------|-------------|
| $f_{\text{HHI}}$ | ✓ | — | ✓ |
| $f_{\text{entropy}}$ | ✓ | — | ✓ |
| $f_{\text{role-dist}}$ | ✓ | ✓ | ✓ |
| $f_{\text{overlap}}$ | ✓ | ✓ | ✓ |
| $f_{\text{sender-only}}$ | ✓ | ✓ | ✓ |
| $f_{\text{receiver-only}}$ | ✓ | ✓ | ✓ |
| $f_{\text{topo}}$ | ✓ | ✓ | ✓ |

Routing features are **never defined per action**, as their signal emerges only
through repeated access patterns.

---

## Fixed Aggregation Policy

All aggregation windows are:
- Deterministic
- Fixed prior to evaluation
- Publicly known to the adversary

No adaptive, data-dependent, or user-conditioned aggregation is permitted.
This restriction ensures that indistinguishability guarantees are evaluated
against a realistic, non-adaptive enterprise adversary.

---

## Role in Evaluation

These features constitute the complete adversarial observable space.
They are provided as inputs to adversarial classifiers whose performance is
evaluated using population-level detectability metrics such as empirical
$\varepsilon$.

No individual feature constitutes a detection decision in isolation.
