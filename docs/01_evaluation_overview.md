# Evaluation Metrics

DeployStega evaluates covert communication using a layered metric suite designed to reflect **realistic adversarial detection** rather than purely linguistic imperceptibility. Metrics are grouped by semantic, behavioral, routing, and population-level detectability.

---

## 1. Population-Level Detectability (Primary Metric)

### Empirical ε (Indistinguishability Parameter)

We adopt a differential-privacy-inspired notion of indistinguishability. Let:

- D be a dataset of benign user logs
- D′ be the same dataset except one (or k) user logs replaced by covert logs
- F(D), F(D′) be the adversarially observable feature sets

An adversary trains a classifier to distinguish F(D) from F(D′).

We define empirical ε as:

\[
\varepsilon_{\text{empirical}} = \ln\left(\frac{\text{TPR}}{\text{FPR}}\right)
\]

Where:
- TPR = true positive rate (covert users flagged)
- FPR = false positive rate (benign users flagged)

**Interpretation**:
- Small ε → covert users blend into the population
- Large ε → covert users are detectably anomalous

This is the **primary deployment metric** for DeployStega.

---

## 2. Semantic Imperceptibility Metrics

These metrics evaluate whether steganographic text deviates from natural language distributions.

### Distributional Metrics
- **Perplexity** under a pretrained LM
- **KL divergence** between next-token distributions (stego vs benign)
- **Embedding distance** (cosine distance between sentence embeddings)

### Linguistic Quality Metrics
- **BERTScore**
- **BLEU / ROUGE** (supporting)
- Optional **human naturalness judgments**

These metrics allow comparison with prior LLM-based steganography systems, but are insufficient alone for security claims.

---

## 3. Behavioral & Temporal Metrics

These metrics capture whether a user’s *actions* resemble benign platform behavior.

### Timing Metrics
- Inter-event time distributions
- Session duration distributions
- Actions per hour / per day

Distances measured using:
- Kolmogorov–Smirnov (KS) distance
- Wasserstein distance

### Interaction Coupling Metrics
- Sender→receiver latency
- Receiver→sender latency
- Bi-directional temporal correlation (Cabuk et al.)

---

## 4. Routing & Interaction Topology Metrics

These metrics measure whether covert users traverse the application similarly to benign users.

- Artifact-class transition distributions
- Markov chain divergence over artifact sequences
- Access-topology similarity (graph-based distance)

Routing observables ensure that dead-drop access patterns do not create detectable navigation anomalies.

---

## 5. Classifier Performance Metrics (Supporting ε)

To contextualize ε, we also report:

- ROC-AUC
- Precision at fixed FPR
- Recall at fixed FPR
- Brier score (calibration)

These metrics help interpret the operational meaning of ε in real monitoring systems.

---

## 6. Throughput Metrics

We measure the cost of indistinguishability in terms of capacity:

- Bits per message
- Bits per session
- Bits per hour

Throughput is always reported jointly with ε to capture the stealth–capacity trade-off.

---

## 7. Population Scaling Metrics

For k covert users:

- ε(k) vs k curve
- Detection threshold k\* at which ε exceeds a practical bound

This evaluates how covert communication scales with user density.
