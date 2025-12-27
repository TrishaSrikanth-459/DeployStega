# Deterministic Dead-Drop Resolver

## Purpose

This module specifies the **deterministic dead-drop routing function** used by DeployStega.  
The resolver maps shared cryptographic inputs and pre-established experimental artifacts to a **concrete, existing GitHub artifact identifier** and a **role-specific URL** at a given epoch `t`.

The resolver guarantees that sender and receiver independently derive:

- the **same artifact identifier tuple**, and  
- **different, role-appropriate URLs** (mutation vs. observation),

while ensuring that all resolved actions and URLs are **behaviorally feasible** under empirically learned benign GitHub interaction traces.

The resolver performs **no behavioral scheduling, network access, or live state queries**. It is a pure, deterministic function evaluated within externally supplied feasibility constraints.

---

## Scope and Non-Goals

### In Scope
- Deterministic resolution from shared inputs to:
  - a GitHub artifact class
  - an **existing identifier tuple** drawn from a fixed repository snapshot
- Deterministic slicing of a shared digest into identifier fields
- Role-specific URL resolution (sender vs. receiver)
- Enforcement of structural and behavioral feasibility constraints at resolution time

### Out of Scope
- Payload encoding or decoding
- Behavioral timing generation or session scheduling
- Network access, permissions, or API calls
- Retransmission, acknowledgment, or delivery guarantees
- Modeling repository evolution or adversarial interference during execution

---

## Fixed Repository Snapshot Assumption

The resolver operates relative to a **fixed repository snapshot** established *prior to the experiment*.

The snapshot is used **only during construction of the resolver**, not exchanged dynamically and not accessed at runtime.

The snapshot defines:
- repository identity (`owner`, `repo`)
- the routing namespace `N` (artifact classes)
- the **set of existing artifact identifiers** per class
- stable identifier schemas
- empirical identifier bounds and frequencies

### Snapshot Integrity Assumption

After the snapshot is fixed:

- No external actor mutates the repository in a way that affects:
  - artifact existence
  - identifier stability
  - namespace structure
- Specifically, artifacts referenced by the resolver are not deleted, transferred, renumbered, or rewritten by third parties during the experiment.

This assumption is adopted to:
- prevent silent message loss unrelated to detectability,
- avoid live repository queries that would introduce observable log artifacts,
- isolate routing detectability from availability failures.

If violated, correctness is not guaranteed; this tradeoff is explicitly accepted for a controlled, population-level detectability evaluation.

---

## Behavioral Feasibility Region (Separate from Snapshot)

The **behavioral feasibility region** is **not** part of the repository snapshot.

It is learned independently from benign GitHub interaction logs and defines which artifact classes and URLs are accessed at specific times, as well as 
the latency relationships between actions across users.

Formally, the feasibility region constrains **time-indexed action tuples**:

(time_window, artifactClass, URL_role)

This region governs *when* a specific URL may be accessed or mutated without deviating from benign behavior.

---

## Separation of Construction vs. Deployment

### Resolver Construction (Offline)

The resolver is built using:
- the fixed repository snapshot (existence + identifiers),
- the routing namespace `N`,
- the benign behavioral feasibility region `R`.

These inputs define the **allowable resolution space**.

### Resolver Deployment (Runtime)

During deployment, the sender and receiver provide only:
- epoch index `t`,
- `senderID`,
- `receiverID`,
- role (`sender` or `receiver`).

The resolver **does not recompute feasibility or consult state** at runtime; it applies precomputed constraints.

---

## Inputs (Runtime)

All runtime inputs are shared out-of-band:

- **Epoch `t`**  
  An index into a behaviorally feasible time window.

- **Sender identifier `senderID`**  
  Stable identifier for the sender.

- **Receiver identifier `receiverID`**  
  Stable identifier for the receiver.

- **Role**  
  Either `sender` or `receiver`.

---

## Outputs

At epoch `t`, the resolver outputs:

- artifact class `C ∈ N`,
- an **existing identifier tuple**
- and **role-specific canonical GitHub URL** from the snapshot,
All objects are behaviorally feasible at epoch `t`.

Formally:

Route(t, role) = (artifactClass, identifierTuple, URL_role)

---

## Deterministic PRNG Core

### PRNG Selection

A cryptographic hash function `H` is used as a **deterministic pseudo-random generator**, providing:

- reproducibility,
- uniform dispersion over snapshot-defined choices,
- independence across epochs.

The PRNG is **never used to invent identifiers**, only to select among existing, snapshot-defined ones.

### PRNG Interface

The shared digest is computed as:

digest = H(t, senderID, receiverID)

All resolution decisions derive from fixed slices of this digest.

---

## Digest Slicing and Artifact Resolution

### Artifact Class Selection

The first 8 bytes of the digest select the artifact class:

classIndex = int(digest[0:8]) mod |N|
artifactClass = N[classIndex]

This indexing applies **only** to the fixed artifact-class namespace `N`.

---

### Identifier Field Slicing

Subsequent, non-overlapping slices of the digest are used to populate identifier fields.

- primary = int(digest[ 8:16])
- secondary = int(digest[16:24])
- tertiary = int(digest[24:32])
- quaternary = int(digest[32:40])
- quinary = int(digest[40:48])

Slices are assigned in order according to the identifier schema of the selected artifact class.

---

### Identifier Instantiation Rules

For an artifact class requiring `k` numeric identifier fields (`2 ≤ k ≤ 5`):

f_i = (slice_i mod MaxF_i(repoSnapshot)) + 1

The resulting identifier tuple is:

(repoId, f1 [, f2 [, f3 [, f4 [, f5 ]]]])

---

## Sender vs. Receiver URL Resolution

The resolver is **role-aware but identifier-consistent**.

- Sender and receiver resolve the **same identifier tuple**.
- They resolve it to **different URLs**, reflecting benign roles.

---

## URL Resolution Under Behavioral Constraints

URL selection is constrained by the behavioral feasibility region:

(URL_role ∈ R) ∧ (t ∈ admissible_time_window(URL_role))

The resolver never outputs a URL outside the feasibility region.

---

## Collision Handling

If a digest-derived selection violates snapshot or feasibility constraints:

- a deterministic rehashing rule is applied,
- resolution repeats until a valid triple is found.

---

## Resolver API

ResolveDeadDrop(t, senderID, receiverID, role)
→ { artifactClass, identifierTuple, canonicalURL }

---

## Determinism Guarantees

- Identical inputs yield identical outputs
- No live state queries
- No runtime enumeration
- Sender and receiver remain synchronized

---

## Assumptions and Limitations

### Assumptions
- Fixed repository snapshot
- Accurate behavioral feasibility region
- Out-of-band key and parameter sharing

### Limitations
- No delivery guarantees
- No repository evolution handling
- No behavioral scheduling
- No adversarial interference modeling

---

## Summary

The deterministic dead-drop resolver maps shared cryptographic inputs to
**existing GitHub artifact identifiers** and **role-specific, behaviorally
feasible URLs**. By separating repository structure, behavioral feasibility,
and runtime resolution, it enables asynchronous covert routing that is
structurally valid, behaviorally indistinguishable, and reproducible—without
live state queries, enumeration, or sender–receiver coordination.
