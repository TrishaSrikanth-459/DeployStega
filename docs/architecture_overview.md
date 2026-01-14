# DeployStega Codebase — File-by-File Architecture Guide

This document provides a **complete, file-level overview** of the DeployStega codebase.
Each file is listed exactly once, with a concise explanation of:

- **What it represents**
- **What responsibility it has**
- **How it is used in the pipeline**

This is an internal architectural reference.

---

## Dataset Layer (`dataset/`)

This package defines the **authoritative data model** used throughout DeployStega.

### `interaction_event.py`
Defines `InteractionEvent`, the smallest adversary-observable unit.

Represents a **single log entry** an adversary could observe.

Used by:
- `routing_trace_to_interaction.py`
- Feature extractors

---

### `interaction_trace.py`
Defines `InteractionTrace`, an immutable ordered sequence of `InteractionEvent`s.

Represents **one user’s complete interaction history**.

Used by:
- `BenignDataset`
- `NeighboringDataset`
- Feature pipelines

---

### `benign_dataset.py`
Defines `BenignDataset`.

An immutable collection of `InteractionTrace`s representing dataset **D**.

Used by:
- Feature extraction
- Neighboring dataset construction
- Evaluation logic

---

### `neighboring_dataset.py`
Defines `NeighboringDataset`.

Wraps a `BenignDataset` and replaces exactly *k* user traces.
Represents dataset **D′**.

Used by:
- Differential privacy experiments
- Adversarial indistinguishability testing

---

### `routing_trace_record.py`
Defines `RoutingTraceRecord`.

Represents **one routing decision** emitted by the resolver.

Responsibilities:
- Parse routing JSONL
- Validate required fields
- Normalize identifiers
- Preserve URLs exactly

Used by:
- `routing_trace_to_interaction.py`
- Inspection and conversion scripts

---

### `routing_trace_to_interaction.py`
Converts routing records into adversary-visible logs.

Responsibilities:
- `RoutingTraceRecord → InteractionEvent`
- Group events by user
- Build `InteractionTrace`s
- Optionally synthesize timestamps deterministically

This is the **boundary between routing output and dataset construction**.

---

### `build_neighboring_dataset_from_routing.py`
Bridges routing traces into datasets.

Responsibilities:
- Load routing JSONL
- Build interaction traces
- Construct `BenignDataset`
- Construct `NeighboringDataset`
- Enforce exact-k replacement semantics

Used by:
- End-to-end experiments
- Dataset validation tests

---

## Routing Layer (`routing/`)

Defines how platform artifacts are deterministically selected.

### `dead_drop_function/dead_drop_resolver.py`
Implements deterministic dead-drop routing.

Maps `(epoch, shared seed)` → artifact identifier.

Used by:
- Interactive console
- Automated routing scripts

---

### `dead_drop_function/github_url_builder.py`
Constructs concrete GitHub URLs from artifact identifiers.

Ensures URLs are stable and reproducible.

Used by:
- Resolver
- Routing trace logging

---

### `dead_drop_function/repository_snapshot/`
Represents a frozen view of repository structure.

Ensures routing only targets existing artifacts.

Used by:
- Resolver
- Experiment context

---

### `feasibility_region.py`
Defines the `FeasibilityRegion` interface.

Accepts or rejects **exact URLs** per epoch.

Used by:
- Resolver
- Behavioral constraint modeling

---

### `trace_weighted_feasibility.py`
Temporary allow-all feasibility region.

Exists to allow routing before empirical traces exist.

Used by:
- Early-stage integration
- Interactive testing

---

### `routing_trace.py`
Defines the routing trace abstraction.

Represents resolver output before conversion into interaction logs.

Used by:
- Routing trace logging
- Conversion scripts

---

## Feature Extraction (`features/`)

Defines the adversary’s observation capabilities.

### `extractor.py`
Defines the abstract `FeatureExtractor`.

Properties:
- Deterministic
- Dataset-agnostic
- No side effects

Implemented by concrete feature extractors.

---

### `feature_set.py`
Defines `FeatureSet`.

Immutable mapping from feature name to extracted value.

Represents the **entire adversary observation**.

---

### `pipeline.py`
Defines `FeatureExtractionPipeline`.

Applies a fixed set of feature extractors to a dataset.

Used by:
- Evaluation scripts
- Experimental analysis

---

## Experiments (`experiments/`)

Defines **what** an experiment is.

### `experiment_manifest.json`
Canonical experiment configuration.

Defines:
- Experiment ID
- Epoch schedule
- Roles
- Routing parameters
- Snapshot reference

Read by:
- `experiment_context.py`

---

## Scripts (`scripts/`)

Defines **how experiments are executed**.

### `experiment_context.py`
Loads and validates experiment configuration.

Wires together:
- Snapshot
- Routing
- Feasibility

Used by:
- Interactive console
- Automated scripts

---

### `interactive_dead_drop.py`
Interactive routing console.

Responsibilities:
- Countdown to epoch start
- Role selection
- Identity verification
- Routing execution
- Routing trace logging

Primary tool for **manual execution**.

---

### `convert_routing_trace.py`
CLI utility for converting routing traces into datasets.

Used to:
- Validate routing → dataset conversion
- Debug dataset construction

---

### `inspect_routing_conversion.py`
Inspection utility.

Prints:
- RoutingTraceRecords
- InteractionEvents
- InteractionTraces
- Dataset structure

Used to **see exactly what gets built**.

---

### `build_snapshot.py`
Builds repository snapshot files.

Queries GitHub metadata and writes immutable snapshots.

Used before experiments.

---

## Tests (`tests/`)

Ensures correctness and invariants.

### `test_dataset_construction.py`
Tests:
- BenignDataset immutability
- Indexing behavior

---

### `test_neighboring_dataset.py`
Tests:
- Exact-k replacement
- Dataset size invariance
- Index transparency

---

### `test_routing_trace_to_event.py`
Tests:
- Single-record conversion
- Timestamp handling
- Action type mapping

---

### `test_routing_trace_to_trace.py`
Tests:
- Event ordering
- Trace construction
- Deterministic sorting

---

### `test_end_to_end_conversion.py`
Tests:
- Routing JSONL → dataset pipeline
- Full structural correctness

---

## How to Run Tests

Run all tests from the repository root:
```
pytest
```

## How to Inspect Routing Conversion Output

To inspect exactly what an `InteractionEvent`, `InteractionTrace`, and dataset look like when converted from a routing trace:
```
python -m scripts.inspect_routing_conversion \
  --routing-trace experiments/routing_trace.jsonl
```

If the routing trace does not contain timestamps, provide deterministic timing parameters:
```
python -m scripts.inspect_routing_conversion \
  --routing-trace experiments/routing_trace.jsonl \
  --epoch-origin-unix <unix_time> \
  --epoch-duration-seconds <seconds>
```

This command will print:

* Parsed `RoutingTraceRecord`s
* Generated `InteractionEvent`s
* Constructed `InteractionTrace`s grouped by user
* Dataset-level summaries

No files are modified; this is a read-only inspection utility.

# System Architecture Diagram

The diagram below shows the end-to-end dataflow in DeployStega, from routing decisions to adversary-visible features.

* Rectangles represent immutable data objects
* Rounded nodes represent deterministic transformations
* No component mutates upstream data

flowchart LR
    %% Routing Output
    subgraph Routing[Routing Layer]
        R1[DeadDropResolver]
        R2[GitHubURLBuilder]
        R3[FeasibilityRegion]
        RT[RoutingTrace JSONL]
    end

    %% Routing Record Layer
    subgraph Records[Routing Trace Records]
        RR[RoutingTraceRecord]
    end

    %% Interaction Layer
    subgraph Interaction[Interaction Construction]
        IE[InteractionEvent]
        IT[InteractionTrace]
    end

    %% Dataset Layer
    subgraph Dataset[Dataset Construction]
        BD[BenignDataset D]
        ND[NeighboringDataset D_prime]
    end

    %% Feature Extraction
    subgraph Features[Adversarial Feature Extraction]
        FE[FeatureExtractors]
        FS[FeatureSet]
    end

    %% Data Flow
    R1 --> R2
    R2 --> R3
    R3 --> RT

    RT --> RR
    RR --> IE
    IE --> IT

    IT --> BD
    BD --> ND

    BD --> FE
    ND --> FE
    FE --> FS

