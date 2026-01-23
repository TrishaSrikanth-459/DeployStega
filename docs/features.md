# DeployStega Feature Set Specification

This document formally defines the adversarial feature space $F$ used in the
DeployStega framework. Features represent all semantic, behavioral, and routing
observables realistically accessible to an adversary via application-level logs.

We distinguish **features**, which are inputs to adversarial classifiers, from
**metrics**, which quantify the adversary’s detection performance. This document
enumerates features only.

---

## Notation

Let:
- $D$ denote a dataset of benign user interaction logs
- $D'$ denote a dataset where one or more users are replaced with covert users
- $\ell \in D \cup D'$ denote a single user log
- $F(\ell) \in \mathbb{R}^d$ denote the feature vector extracted from log $\ell$

The adversary’s capability class is defined as:

$$
\mathcal{F}
=
\mathcal{F}_{\text{semantic}}
\cup
\mathcal{F}_{\text{behavioral}}
\cup
\mathcal{F}_{\text{routing}}
$$

---

## Semantic Feature Space $\mathcal{F}_{\text{semantic}}$

Semantic features capture linguistic deviations introduced by steganographic
encoding. These features are computed over user-generated text artifacts.

| Feature Name | Symbol | Description |
|-------------|--------|-------------|
| Perplexity | $f_{\text{ppl}}$ | Average token-level perplexity under a reference language model |
| Token-level KL divergence | $f_{\text{KL}}$ | KL divergence between next-token distributions under two contexts |
| Sentence embedding | $f_{\text{emb}}$ | Normalized sentence embedding vector (e.g., SBERT) |
| Embedding distance | $f_{\text{emb-dist}}$ | Pairwise cosine distance between embeddings |
| Token count | $f_{\text{len}}$ | Number of tokens in message |

Semantic features are extracted per message and may be aggregated per session or user.

---

## Behavioral Feature Space $\mathcal{F}_{\text{behavioral}}$

Behavioral features capture temporal and structural properties of user interaction
patterns observable through application logs.

### Timing and Session Features

| Feature Name | Symbol | Description |
|-------------|--------|-------------|
| Inter-event time | $f_t$ | Time gap between consecutive user actions |
| Session length | $f_{\text{sess}}$ | Duration of user sessions |
| Action frequency | $f_{\text{freq}}$ | Actions per unit time (hour/day) |

### Interaction Structure

| Feature Name | Symbol | Description |
|-------------|--------|-------------|
| Event-type frequency | $f_{\text{etype}}$ | Distribution over action types (comment, edit, view, etc.) |
| Artifact revisit rate | $f_{\text{revisit}}$ | Probability of re-accessing the same artifact |
| Artifact transition | $f_{\text{trans}}$ | Transition probabilities between artifact classes |

### Cross-User Timing Correlation

| Feature Name | Symbol | Description |
|-------------|--------|-------------|
| Sender → receiver latency | $f_{\text{review-lat}}$ | Time between sender modification and receiver access |
| Retrieval latency | $f_{\text{retr-lat}}$ | Time between artifact update and later retrieval |
| Temporal correlation | $f_{\text{corr}}$ | Bi-directional timing correlation between users |

---

## Routing Feature Space $\mathcal{F}_{\text{routing}}$

Routing features capture how users navigate application artifacts and how sender
and receiver behaviors overlap at the artifact-identity level.

### Identifier-Level Concentration

| Feature Name | Symbol | Description |
|-------------|--------|-------------|
| Identifier concentration (HHI) | $f_{\text{HHI}}$ | Herfindahl–Hirschman Index over accessed artifact IDs |
| Identifier entropy | $f_{\text{entropy}}$ | Normalized entropy of artifact ID access distribution |

### Role-Asymmetric Routing

| Feature Name | Symbol | Description |
|-------------|--------|-------------|
| Role artifact distribution | $f_{\text{role-dist}}$ | Divergence between sender and receiver distributions over artifact classes |

### Shared Access and Topology

| Feature Name | Symbol | Description |
|-------------|--------|-------------|
| Shared artifact overlap | $f_{\text{overlap}}$ | Fraction of artifact IDs accessed by both roles |
| Sender-only fraction | $f_{\text{sender-only}}$ | Artifacts accessed exclusively by sender |
| Receiver-only fraction | $f_{\text{receiver-only}}$ | Artifacts accessed exclusively by receiver |
| Shared topology profile | $f_{\text{topo}}$ | Vector of shared vs exclusive artifact access proportions |

Routing features are multi-user observables and are uniquely induced by
application-layer dead-drop communication.

---

## Feature Aggregation and Windows

Features may be extracted at multiple granularities:
- Per action
- Per session
- Per epoch
- Per user

Aggregation functions include:
- Mean
- Variance
- Quantiles
- Histograms

All aggregation windows are fixed and known to the adversary.

---

## Role in Evaluation

These features form the complete adversarial observable space.
They are provided as inputs to adversarial classifiers whose performance
is evaluated using population-level detectability metrics such as empirical $\varepsilon$.

No feature directly constitutes a detection decision.
