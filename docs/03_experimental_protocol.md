# Experimental Protocol

DeployStega evaluates covert communication using a controlled dataset-construction pipeline designed to isolate the effect of covert behavior under realistic constraints.

---

## Step 1: Construct Benign Dataset D

We construct a multi-user dataset D from real GitHub activity logs drawn from GH Archive.

From these logs, we extract empirical distributions for:
- Timing
- Session structure
- Artifact access patterns
- Interaction latencies

These distributions define the platform’s behavioral baseline.

---

## Step 2: Train Behavioral Prior

We train a multi-scale behavioral model (SeqA-ITD) exclusively on benign logs. This model defines the **behavioral feasibility region** within which covert users must operate.

---

## Step 3: Generate Covert Behavioral Traces

For a covert user:
- A full interaction schedule is sampled from the behavioral prior
- All semantic and routing actions must occur strictly within this schedule

---

## Step 4: Apply Semantic Steganography

At each scheduled action:
- A GitHub-style message template is selected
- Token-binning steganography embeds payload bits
- If no viable token exists, embedding is skipped

Payloads may be split across events if needed.

---

## Step 5: Construct Neighboring Dataset D′

D′ differs from D in exactly one user log:
- That user’s real log is removed
- Replaced with synthetic behavioral + semantic + routing logs

All other users remain unchanged.

---

## Step 6: Generate Routing Logs

DeployStega instantiates an application-layer dead-drop channel:
- Sender embeds content into existing artifacts
- Receiver accesses artifacts independently
- Failed decodings are treated as benign reads

Routing metadata populates routing observables in F.

---

## Step 7: Extract Adversarial Features

For both D and D′, we extract:

- Semantic features
- Behavioral features
- Routing features

These form the adversary’s capability class F.

---

## Step 8: Train Adversarial Classifiers

We train three classifiers:

1. Semantic-only → ε_semantic
2. Behavioral-only → ε_behavioral
3. Cross-layer → ε_cross-layer

This functions as a structured ablation study.

---

## Step 9: Compute ε and Supporting Metrics

Classifier outputs are converted into empirical ε and supporting ROC metrics.

---

## Step 10: Population Scaling Analysis

We repeat the pipeline for k ∈ {1,2,3,5,10} covert users to estimate ε(k).
