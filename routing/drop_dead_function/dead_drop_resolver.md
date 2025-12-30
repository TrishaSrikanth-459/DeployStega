# Deterministic Dead-Drop Resolver

## Purpose

This document specifies the deterministic dead-drop routing function used by DeployStega.

The resolver maps shared cryptographic inputs and a pre-established experimental environment to:

- a concrete GitHub artifact class,
- an existing, snapshot-validated identifier tuple, and
- a single, role-appropriate, behaviorally feasible GitHub URL,

at a logical epoch index t.

The resolver guarantees that the sender and receiver independently derive:

- the same artifact identifier tuple, and
- different role-appropriate interaction surfaces (mutation vs. observation),

without runtime coordination, network access, shared clocks, or signaling.

The resolver is a pure deterministic function, evaluated under externally supplied feasibility constraints.

## Scope and Non-Goals

### In Scope

The resolver deterministically maps shared inputs to:

- a GitHub artifact class drawn from a fixed routing namespace,
- an existing identifier tuple drawn from a frozen snapshot,
- a single canonical URL appropriate to the user’s role,

subject to structural and behavioral feasibility constraints.

### Explicitly Out of Scope

The resolver does not perform or model:

- payload encoding or decoding,
- behavioral timing generation or scheduling,
- live epoch synchronization or wall-clock coordination,
- network access, API calls, or permission checks,
- retransmission, acknowledgment, or delivery guarantees,
- repository evolution or adversarial interference.

DeployStega is not a messaging system.  
It is a routing abstraction for detectability analysis.

## Fixed Repository Snapshot Assumption

The resolver operates relative to a fixed repository snapshot established prior to the experiment.

### Snapshot Properties

The snapshot defines:

- repository identity (owner, repo),
- routing namespace N (artifact classes),
- complete sets of existing artifact identifiers per class,
- stable identifier schemas,
- empirically observed identifier bounds and frequencies.

### Snapshot Usage

- Constructed offline.
- Never queried or updated at runtime.
- Shared out-of-band by sender and receiver.

### Snapshot Integrity Assumption

After the snapshot is fixed:

- No artifact referenced by the resolver is deleted, renumbered, rewritten, or transferred.
- No identifier field changes meaning.
- No placeholder or synthetic identifiers exist.

This assumption is adopted to:

- prevent silent message loss unrelated to detectability,
- avoid live repository queries that would introduce observable side effects,
- isolate routing detectability from availability failures.

If violated, correctness is not guaranteed. This tradeoff is explicitly accepted.

## Hard Snapshot Validity Rule (Critical)

The resolver must never output an invalid or non-existent GitHub URL.

Therefore:

- Artifact classes with no valid identifiers in the snapshot are excluded.
- Commit identifiers must include concrete branch and path values.
- Any artifact whose identifier fields are missing, unknown, or invalid is excluded at snapshot construction time, not at resolution time.

Guarantee:  
If the resolver outputs a URL, that URL is syntactically and semantically valid on GitHub.

## Behavioral Feasibility Region

The behavioral feasibility region is learned independently from benign GitHub interaction traces.

It constrains admissible tuples of the form:

- (time_window, artifactClass, role, URL)

The feasibility region governs:

- which artifact classes are plausibly accessed at a given epoch,
- which URLs are plausible for senders vs. receivers,
- latency relationships between mutation and observation.

The resolver never outputs a URL outside this region.

## Separation of Construction vs. Deployment

### Resolver Construction (Offline)

The resolver is constructed using:

- the fixed repository snapshot,
- the routing namespace N,
- the behavioral feasibility region R.

This defines the entire allowable resolution space.

### Resolver Deployment (Runtime)

At runtime, the sender and receiver independently provide only:

- epoch index t,
- senderID,
- receiverID,
- role (sender or receiver).

The resolver performs:

- no enumeration,
- no feasibility learning,
- no network access.

## Runtime Inputs

### Epoch t

A logical index into a behaviorally feasible time window.  
Epochs are analytical indices, not synchronized clocks.

### Sender Identifier (senderID)

A stable, opaque identifier for the sender.

### Receiver Identifier (receiverID)

A stable, opaque identifier for the receiver.

### Role

Either sender or receiver.

## Outputs

At epoch t, the resolver outputs:

- artifact class C ∈ N,
- an existing identifier tuple,
- a single role-appropriate canonical GitHub URL.

Formally:

Route(t, role) = (artifactClass, identifierTuple, URL_role)

All outputs are guaranteed to be:

- snapshot-valid,
- syntactically correct,
- behaviorally feasible at epoch t.

## Deterministic PRNG Core

### PRNG Selection

A cryptographic hash function H is used as a deterministic PRNG, providing:

- reproducibility,
- uniform dispersion over snapshot-defined choices,
- independence across epochs.

The PRNG never invents identifiers.  
It only selects among existing snapshot-defined options.

### PRNG Interface

The shared digest is computed as:

digest = H(t || senderID || receiverID)

All resolution decisions derive from fixed, non-overlapping slices of this digest.

## Artifact Resolution

### Artifact Class Selection

The first slice of the digest selects an artifact class:

classIndex = digest[0:8] mod |N_valid|

Copy code
artifactClass = N_valid[classIndex]


Where N_valid includes only artifact classes with at least one valid identifier.

### Identifier Selection

Subsequent digest slices index directly into the existing identifier list for the selected artifact class.

Entire identifier tuples are selected as atomic units.

This avoids:

- gaps,
- deleted artifacts,
- invalid identifier combinations.

### Sender vs. Receiver URL Resolution

The resolver is role-aware but identifier-consistent.

Sender and receiver resolve the same identifier tuple.

Sender resolves a mutation-capable URL.

Receiver resolves an observation-only URL.

Exactly one URL is returned per resolution.

If no role-appropriate URL exists for an artifact at epoch t, that artifact is excluded.

## Eventual Observability Guarantee (Critical)

DeployStega guarantees eventual observability without coordination:

- Epochs define stable observation windows, not execution times.
- For a given epoch t, resolver output is fixed and repeatable.
- The sender may perform the mutation at any time within epoch t.
- The receiver may observe the artifact at any later time, including:
  - later within epoch t, or
  - during subsequent epochs t+1, t+2, ….

Because:

- identifiers are fixed,
- artifacts persist,
- receiver URLs are observation-only,

the receiver is guaranteed to retrieve the sender’s modification as long as the artifact remains visible, without knowing when the sender acted.

No clocks, acknowledgments, retries, or synchronization are required.

## Timeline (Asynchronous, No Coordination)

Time →

### Pre-Experiment (Offline)

- GitHub token provided
- Repository enumerated
- Snapshot frozen
- Feasibility region learned

↓

### Sender (Independent)

- Resolve(t)
- Mutate artifact at any time within epoch t

↓

### Receiver (Independent)

- Resolve(t)
- Observe artifact at any later time ≥ mutation

There is no runtime synchronization, signaling, or feedback.

## Assumptions and Limitations

### Assumptions

- Fixed repository snapshot.
- Accurate behavioral feasibility region.
- Sender and receiver are collaborators on the repository.
- Out-of-band sharing of parameters.

### Limitations

- No delivery guarantees.
- No repository evolution handling.
- No adversarial interference modeling.
- No real-time behavioral scheduling.

## Summary

The deterministic dead-drop resolver maps shared cryptographic inputs to existing, behaviorally feasible GitHub artifact identifiers and role-specific URLs.

By strictly separating:

- repository structure (snapshot),
- behavioral plausibility (feasibility region),
- runtime resolution (pure deterministic function),

DeployStega enables asynchronous covert routing that is:

- structurally valid,
- behaviorally indistinguishable from benign use,
- reproducible,
- and free from runtime coordination.
