# DeployStega Codebase — Pipeline & Module Guide

This document describes the current structure of the DeployStega codebase, the role of each module, and how data flows through the system **as it exists today**.  
It is intended as an internal architectural guide rather than a user-facing tutorial.

---

## High-Level Pipeline Overview

DeployStega is organized around a **dataset-centric evaluation pipeline**:

1. **Interaction Traces** represent observable platform behavior.
2. **Datasets** group traces into benign and neighboring (DP-style) populations.
3. **Routing logic** generates feasible access patterns.
4. **Feature extraction** maps datasets to adversary-visible observables.
5. **Evaluation** compares benign vs. neighboring datasets using these features.

The system is intentionally modular so that semantic, behavioral, and routing components can be composed or evaluated independently.

---

## Core Data Model (`dataset/`)

The `dataset` package defines the **authoritative representation of platform logs**.

### `interaction_event.py`
Defines `InteractionEvent`, the smallest observable unit:
- timestamp
- action type
- artifact identifiers
- immutable metadata

This corresponds directly to what an adversary could observe in logs.

---

### `interaction_trace.py`
Defines `InteractionTrace`, an **immutable, ordered sequence** of `InteractionEvent`s for a single user.

A trace represents *one user’s complete interaction history* over the measurement window.

---

### `benign_dataset.py`
Defines `BenignDataset`:
- An immutable collection of `InteractionTrace`s
- One trace per user
- Represents dataset **D** in the DP-style formulation

---

### `neighboring_dataset.py`
Defines `NeighboringDataset`:
- Wraps a `BenignDataset`
- Replaces exactly *k* user traces with synthetic or covert traces
- Represents dataset **D′**

Critically:
- Dataset size is unchanged
- Only per-user traces differ
- No feature extractor is aware whether it is operating on D or D′

---

## Routing and Feasibility (`routing/`)

The `routing` package defines **how sender and receiver interact with platform artifacts** while preserving identifier stability and behavioral plausibility.

### `dead_drop_function/`
Implements deterministic routing logic.

Key components:
- `dead_drop_resolver.py`  
  Deterministically maps shared seeds and epochs to artifact identifiers.
- `github_url_builder.py`  
  Constructs concrete GitHub URLs from identifier tuples.
- `repository_snapshot/`  
  Represents a fixed snapshot of repository structure and identifiers.

---

### `feasibility_region.py`
Defines the **FeasibilityRegion interface**:
- Operates strictly at the URL level
- Accepts or rejects *exact* URLs (not simply artifacts) at given epoches
- Encodes behavioral constraints

---

### `trace_weighted_feasibility.py`
Implements a permissive feasibility region placeholder:
- Allows all URLs by default
- Exists to support integration before empirical traces are available
- Will later be replaced by trace-derived allow-lists

---

### `routing_trace.py`
Represents a concrete routing trace produced by:
- Resolver output
- Feasibility filtering
- Role-specific access behavior

Routing traces are later converted into `InteractionTrace`s.

---

## Feature Extraction (`features/`)

The `features` package defines the adversary’s **capability class F**.

### `extractor.py`
Defines the abstract `FeatureExtractor`:
- Deterministic
- Dataset-agnostic (D vs. D′)
- Purely observational
- No side effects

---

### `feature_set.py`
Defines `FeatureSet`:
- Immutable mapping from feature name → extracted values
- Represents the *entire observable output* of an adversary

---

### `pipeline.py`
Defines `FeatureExtractionPipeline`:
- Applies a fixed set of feature extractors to a dataset
- Produces a `FeatureSet`
- Enforces extractor-name uniqueness
- Does not interpret features

---

## Experiments and Scripts

### `experiments/`
Contains experiment configuration artifacts:
- `experiment_manifest.json`
- snapshot definitions

---

### `scripts/`
Contains orchestration utilities:
- snapshot builders
- trace template generators
- experiment context setup

---

## Tests (`tests/`)

Tests are organized by subsystem:
- dataset immutability
- routing determinism
- feasibility enforcement
- feature extraction stability

The test suite enforces:
- determinism
- immutability
- role symmetry
- feasibility correctness

---

## Conceptual Separation Guarantees

The codebase enforces the following separations:

- **Routing vs. Feasibility**  
  Routing chooses identifiers; feasibility only restricts URLs.

- **Behavior vs. Semantics**  
  Timing and access patterns are independent of message content.

- **Dataset vs. Features**  
  Feature extractors never mutate or inspect dataset provenance.

- **Adversary vs. Participants**  
  The adversary observes logs; it does not interact with the repository.

---

## Current Scope Status

At present, the codebase fully supports:
- Deterministic routing
- Dataset construction (D and D′)
- Feature extraction pipelines
- Formal DP-style neighboring datasets

Semantic steganography, behavioral generators, and adversarial classifiers are designed but intentionally modular and not yet integrated.

---

## Intended Audience

This document is written for:
- Project collaborators
- Paper reviewers
- Future maintainers

It assumes familiarity with:
- Differential privacy
- Log-based anomaly detection
- Platform-mediated communication systems

---

## System Architecture Diagram

The following diagram illustrates how DeployStega’s components compose into a
dataset-centric evaluation pipeline. Rectangles represent immutable data
objects; rounded boxes represent deterministic transformations.

```mermaid
flowchart LR
    %% =========================
    %% Raw Interaction Layer
    %% =========================
    subgraph Logs["Raw Platform Logs"]
        E1["InteractionEvent"]
        E2["InteractionEvent"]
        E3["InteractionEvent"]
    end

    %% =========================
    %% Trace Construction
    %% =========================
    subgraph Traces["Per-User Traces"]
        T1["InteractionTrace"]
        T2["InteractionTrace"]
        T3["InteractionTrace"]
    end

    %% =========================
    %% Dataset Layer
    %% =========================
    subgraph Datasets["Dataset Construction"]
        BD["BenignDataset D"]
        ND["NeighboringDataset D_prime"]
    end

    %% =========================
    %% Routing & Feasibility
    %% =========================
    subgraph Routing["Routing and Feasibility"]
        R1["Dead Drop Resolver"]
        R2["GitHub URL Builder"]
        R3["Feasibility Region"]
        RT["Routing Trace"]
    end

    %% =========================
    %% Feature Extraction
    %% =========================
    subgraph Features["Adversarial Feature Extraction"]
        FE["Feature Extractors"]
        FS["FeatureSet"]
    end

    %% =========================
    %% Connections
    %% =========================
    E1 --> T1
    E2 --> T2
    E3 --> T3

    T1 --> BD
    T2 --> BD
    T3 --> BD

    BD --> ND

    R1 --> R2
    R2 --> R3
    R3 --> RT

    RT --> ND

    BD --> FE
    ND --> FE
    FE --> FS
