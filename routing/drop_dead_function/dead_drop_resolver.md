# Deterministic Dead-Drop Resolver

## Purpose

This document specifies the **deterministic dead-drop routing function** used by **DeployStega**.

The resolver maps **shared cryptographic inputs** and a **pre-established experimental environment** to:

- a concrete **GitHub artifact class**,
- an **existing, snapshot-validated identifier tuple**, and
- a **single, role-appropriate, behaviorally feasible GitHub URL**,

at a logical epoch index `t`.

The resolver guarantees that the sender and receiver **independently derive**:

- the **same artifact identifier tuple**, and
- **different role-appropriate interaction surfaces** (mutation vs. observation),

**without runtime coordination, network access, or shared clocks**.

The resolver is a **pure deterministic function** evaluated under **externally supplied feasibility constraints**.

---

## Scope and Non-Goals

### In Scope

The resolver deterministically maps shared inputs to:

- a GitHub artifact class drawn from a fixed routing namespace,
- an **existing identifier tuple drawn from a frozen snapshot**,
- a **single canonical URL appropriate to the user’s role** (sender or receiver),
- subject to **structural and behavioral feasibility constraints**.

### Explicitly Out of Scope

The resolver does **not** perform or model:

- payload encoding or decoding,
- behavioral timing generation or scheduling,
- live epoch synchronization or wall-clock coordination,
- network access, API calls, or permission checks,
- retransmission, acknowledgment, or delivery guarantees,
- repository evolution, deletion, or adversarial interference.

DeployStega is **not** a messaging system or service.  
It is a **routing abstraction for detectability analysis**.

---

## Fixed Repository Snapshot Assumption

The resolver operates relative to a **fixed repository snapshot** established **prior to the experiment**.

### Snapshot Properties

The snapshot defines:

- repository identity `(owner, repo)`,
- the routing namespace `N` (artifact classes),
- the complete set of **existing artifact identifiers per class**,
- **stable identifier schemas** per artifact class,
- empirically observed identifier bounds and frequencies.

### Snapshot Usage

- The snapshot is constructed **offline**.
- It is **never queried, updated, or exchanged at runtime**.
- Sender and receiver are assumed to share the snapshot **out-of-band**.

---

## Snapshot Integrity Assumption

After the snapshot is fixed:

- No artifact referenced by the resolver is deleted, renumbered, rewritten, or transferred.
- No identifier field (e.g., issue number, commit SHA, branch, path) changes meaning.
- No placeholder or synthetic identifiers (e.g., `"unknown"`) exist in the snapshot.

This assumption is adopted to:

- prevent silent message loss unrelated to detectability,
- avoid live repository queries that would introduce observable side effects,
- isolate routing detectability from availability failures.

If violated, correctness is **not guaranteed**.  
This tradeoff is **explicitly accepted** for controlled, population-level detectability evaluation.

---

## Hard Snapshot Validity Rule (Critical)

The resolver **will never** output an identifier or URL that is not **concretely valid on GitHub**.

Therefore:

- Artifact classes with **no valid identifiers** in the snapshot are excluded from routing.
- Commit identifiers **must include concrete `branch` and `path` values**.
- Any artifact whose identifier fields are missing, invalid, or non-addressable is **excluded at snapshot construction time**, not at resolution time.

> **If the resolver outputs a URL, that URL is syntactically and semantically valid on GitHub.**

---

## Behavioral Feasibility Region (Separate from Snapshot)

The **behavioral feasibility region** is distinct from the snapshot.

It is learned independently from **benign GitHub interaction traces** and constrains **when** and **how** artifacts may be accessed or mutated.

Formally, it defines admissible tuples:

(time_window, artifactClass, role, URL)

The feasibility region governs:

- which artifact classes are plausibly accessed at a given epoch,
- which URLs are plausible for **senders vs. receivers**,
- latency relationships between mutation and observation.

The resolver **never outputs a URL outside this region**.

---

## Separation of Construction vs. Deployment

### Resolver Construction (Offline)

The resolver is constructed using:

- the fixed repository snapshot,
- the routing namespace `N`,
- the behavioral feasibility region `R`.

This defines the **entire allowable resolution space**.

No runtime information is required beyond shared inputs.

---

### Resolver Deployment (Runtime)

At runtime, the sender and receiver independently provide only:

- epoch index `t`,
- `senderID`,
- `receiverID`,
- role (`sender` or `receiver`).

The resolver:

- performs **no enumeration**,
- performs **no feasibility learning**,
- performs **no network access**.

It applies **precomputed constraints only**.

---

## Runtime Inputs

All runtime inputs are shared **out-of-band** and fixed for the experiment.

- **Epoch `t`**  
  A logical index into a behaviorally feasible time window.  
  Epochs are analytical indices, **not synchronized clocks**.

- **Sender Identifier `senderID`**  
  A stable, opaque identifier for the sender.

- **Receiver Identifier `receiverID`**  
  A stable, opaque identifier for the receiver.

- **Role**  
  Either `sender` or `receiver`.

---

## Outputs

At epoch `t`, the resolver outputs:

- artifact class `C ∈ N`,
- an **existing identifier tuple**,
- a **single role-appropriate canonical GitHub URL**.

Formally:

Route(t, role) = (artifactClass, identifierTuple, URL_role)

All outputs are guaranteed to be:

- snapshot-valid,
- syntactically correct,
- behaviorally feasible at epoch `t`.

---

## Deterministic PRNG Core

### PRNG Selection

A cryptographic hash function `H` is used as a deterministic PRNG, providing:

- reproducibility,
- uniform dispersion over snapshot-defined choices,
- independence across epochs.

The PRNG **never invents identifiers**.  
It only selects among **existing snapshot-defined options**.

---

### PRNG Interface

The shared digest is computed as:

digest = H(t || senderID || receiverID)

All resolution decisions derive from **fixed slices** of this digest.

---

## Artifact Resolution

### Artifact Class Selection

The first slice of the digest selects an artifact class:

classIndex = digest[0:8] mod |N_valid|
artifactClass = N_valid[classIndex]

Where `N_valid` includes **only artifact classes with at least one valid identifier**.

---

### Identifier Selection

Subsequent non-overlapping digest slices index into the **existing identifier set** for the selected class.

The resolver selects **entire identifier tuples** from the snapshot.

This avoids:

- gaps,
- deleted artifacts,
- invalid combinations.

---

## Sender vs. Receiver URL Resolution

The resolver is **role-aware but identifier-consistent**.

- Sender and receiver resolve the **same identifier tuple**.
- They resolve it to **different URLs**, reflecting benign platform roles.

### URL Rules

- **Sender URLs** correspond to mutation-capable surfaces.
- **Receiver URLs** correspond to observation-only surfaces.
- **Exactly one URL** is returned per resolution.

If no role-appropriate URL exists for an artifact at epoch `t`, that artifact is excluded.

---

## Collision and Infeasibility Handling

If a digest-derived candidate violates:

- snapshot validity, or
- behavioral feasibility constraints,

then:

- a deterministic rehashing rule is applied,
- resolution repeats until a valid triple is found.

This process is deterministic and side-effect free.

---

## Receiver-Side Verification Without Coordination

DeployStega does not guarantee that the receiver accesses the correct artifact *at the exact moment* the sender mutates it.
Instead, it provides **verifiable rendezvous candidates**.

### Decode-or-Discard Rule

For any resolved candidate artifact:

1. The receiver accesses the artifact via `URL_receiver`.
2. The receiver extracts the candidate payload from the artifact content.
3. The receiver attempts to decode the payload.
4. If decoding fails cryptographic verification, the artifact is treated as **benign**.
5. If decoding succeeds verification, the artifact is accepted as the **sender’s message**.

This decision is local, deterministic, and requires **no acknowledgments or feedback**.

---

### Self-Authenticating Payload Requirement

Payloads are **self-authenticating** under a key shared out-of-band.

A payload is accepted **if and only if** cryptographic verification succeeds.

This prevents false positives from:

- unrelated user activity,
- background noise,
- accidental matches.

---

### Eventual Observability (Conditional)

DeployStega does **not** guarantee unconditional delivery.

Instead, it guarantees **eventual observability under a receiver search policy**:

- Resolver output for a given epoch `t` is fixed and repeatable.
- Artifact identifiers persist after mutation.
- Receiver URLs are observation-only and safe to revisit.
- The receiver stops upon the first authenticated decode.

Verification converts retrieval into a **search with a definitive stopping condition**, not a delivery guarantee.

---
## Receiver Epoch Inspection Window

The receiver may deterministically resolve and inspect artifacts corresponding to a **fixed, finite window of past epochs** based on behavioral constraints.

Specifically, at logical time **T**, the receiver is permitted to evaluate resolver outputs for epochs:

t ∈ [T − W, T]

where **W** is an experiment-defined constant (e.g., **W = 20** epochs). 

Each inspected epoch yields exactly one snapshot-valid, observation-only URL. Epochs outside this window are never inspected.

---

## Timeline (Asynchronous, No Coordination)

PRE-EXPERIMENT (OFFLINE)
┌──────────────────────────────────────────────────────────────┐
│ - GitHub token provided │
│ - Repository enumerated │
│ - Snapshot frozen │
│ - Feasibility region learned │
└──────────────────────────────────────────────────────────────┘

EXPERIMENT
┌──────────────────────┐ ┌──────────────────────┐
│ Sender (independent) │ │ Receiver (independent)│
│ │ │ │
│ Resolve(t) │ │ Resolve(t) │
│ Mutate artifact │ │ Observe artifact │
│ at some time within │ │ at any later time │
│ epoch t │ │ (t, t+1, t+2, …) │
└──────────────────────┘ └──────────────────────┘


There is **no runtime synchronization**, acknowledgment, or feedback.

---

## Assumptions and Limitations

### Assumptions

- Fixed repository snapshot.
- Accurate behavioral feasibility region.
- Sender and receiver are collaborators of the repository.
- Out-of-band sharing of snapshot parameters and steganographic decoding keys.

### Limitations

- No delivery guarantees.
- No handling of repository evolution.
- No modeling of adversarial interference.
- No behavioral scheduling or traffic shaping.

---

## Summary

The deterministic dead-drop resolver maps shared cryptographic inputs to **existing, behaviorally feasible GitHub artifact identifiers and role-specific URLs**.

By strictly separating:

- repository structure (snapshot),
- behavioral plausibility (feasibility region),
- runtime resolution (pure function),
- and receiver-side cryptographic verification,

DeployStega enables **asynchronous covert routing** that is:

- structurally valid,
- behaviorally indistinguishable from benign use,
- verifiable without coordination,
- and suitable for rigorous detectability evaluation.

The system intentionally provides **verifiable rendezvous**, not guaranteed delivery, enabling honest analysis without conflating routing with messaging.
