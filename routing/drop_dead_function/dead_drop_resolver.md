# Deterministic Dead-Drop Resolver

## Purpose

This document specifies the **deterministic dead-drop routing function** used by **DeployStega**.

The resolver maps **shared cryptographic inputs** and a **pre-established experimental environment** to:

- a concrete **GitHub artifact class**,
- an **existing, snapshot-validated identifier tuple**, and
- a **single, role-appropriate, behaviorally feasible GitHub URL**,

at a logical epoch index `t`.

For every valid epoch `t`, the resolver guarantees that the sender and receiver independently derive:

- the **same artifact identifier tuple**, and
- **different role-appropriate interaction surfaces** (mutation vs. observation),

without runtime communication, acknowledgments, or feedback.

The resolver is a **pure deterministic function** evaluated under externally supplied feasibility constraints.

---

## What Is Shared Out-of-Band

DeployStega **requires** a limited, well-defined set of out-of-band agreements established **before** the experiment.

The following items **are shared out of band**:

- the **repository snapshot**,
- the **dead-drop resolver algorithm**,
- the **steganographic encoding algorithm** (sender only),
- the **steganographic decoding key** (receiver only),
- the **epoch definition**, including:
  - epoch duration,
  - a **fixed epoch origin time `T₀`**,
  - a **fixed epoch end time `T_end`** defining the termination of the covert communication session,
  - epoch inspection window size `W`.
    
The following items are **not shared out of band**:

- the steganographic payload itself,
- which epochs contain payloads,
- which artifacts carry payloads,
- whether any given epoch contains a payload at all.

DeployStega does **not** attempt to conceal these setup assumptions.  
They are exchanged privately and are **explicitly outside the threat model**.

---

## Epoch Definition (Critical Clarification)

### Logical Epochs

An **epoch** is a logical index defined as:

t = floor((current_unix_time − T₀) / epoch_duration_seconds)

where:

- **`T₀`** is a fixed Unix timestamp agreed upon out of band,
- **`epoch_duration_seconds`** is fixed for the experiment,
- **`current_unix_time`** is obtained locally at runtime.

Epochs are **indices, not events**:

- They do not imply that a sender posted.
- They do not imply that a receiver read.
- They exist solely to parameterize deterministic resolution.

Epoch counting begins at the fixed origin time `T₀`.  
Running any script does **not** reset epoch indices.

---

## Mandatory Epoch Participation (Capture Guarantee)

For the duration of the experiment, **epoch participation is mandatory**.

The protocol enforces the following rules:

- **For every epoch `t`, the resolver is evaluated by both sender and receiver.**
- If the feasibility region yields **no admissible URL** for a given role at epoch `t`,
  that role performs **no routing action** for that epoch.
- Otherwise, the role performs **exactly one interaction attempt** derived from the resolver output.

Participants **do not choose** which epochs to visit; they **must** follow the resolver’s output exactly.
Participants are **explicitly forbidden** from visiting any repository URLs outside those produced by the resolver for the current epoch.

### Capture Guarantee (Conditional)

Under these rules, DeployStega guarantees:

> **If the sender embeds a payload in epoch `t`, and both sender and receiver correctly execute all resolver-directed actions for every epoch in their session, then the receiver will observe and decode that payload.**

This guarantee holds provided that:

- the artifact persists,
- GitHub access succeeds,
- the feasibility region correctly enforces sender-before-receiver ordering.
- steganographic decoding is successful

No probabilistic inspection or missed-epoch recovery is required under correct participation.

---

## Fixed Repository Snapshot Assumption

The resolver operates relative to a **fixed repository snapshot** established **prior to the experiment**.

### Snapshot Properties

The snapshot defines:

- repository identity `(owner, repo)`,
- the routing namespace `N`,
- the complete set of **existing artifact identifiers per class**,
- stable identifier schemas.

### Hard Snapshot Validity Rule

The resolver **never outputs invalid or non-addressable URLs**.

Therefore:

- artifact classes with zero valid identifiers are excluded,
- placeholder identifiers (e.g., `"unknown"`) are forbidden.

If the resolver outputs a URL, that URL is **guaranteed valid on GitHub** at snapshot time.

---

## Behavioral Feasibility Region

The behavioral feasibility region constrains admissible tuples of the form:

(epoch_window, artifactClass, role, URL)

The resolver **never emits URLs outside this region**.

The feasibility region additionally enforces **temporal ordering constraints**, including:

- minimum delay between sender mutation and receiver observation,
- receiver-side access latency consistent with benign behavior.

These constraints ensure that the receiver **never attempts to read an artifact while it is being mutated**, eliminating race conditions and missed observations.

---

## Resolver Inputs (Runtime)

At runtime, each party independently provides:

- epoch index `t` (derived from `T₀`),
- `senderID`,
- `receiverID`,
- role (`sender` or `receiver`).

No other runtime input or communication occurs.

---

## Resolver Outputs

For each `(t, role)`, the resolver outputs **at most one** triple:

(artifactClass, identifierTuple, URL_role)

All outputs are:

- snapshot-valid,
- behaviorally feasible,
- deterministic.

If no feasible URL exists for `(t, role)`, the resolver outputs **no action**.

---

## Deterministic PRNG

A cryptographic hash function `H` is used as a deterministic PRNG:

digest = H(t || senderID || receiverID)

All selection decisions derive from fixed slices of this digest.

The PRNG **never invents identifiers**.  
It indexes only into snapshot-defined artifacts.

---

## Sender vs. Receiver Resolution

- Sender and receiver resolve the **same identifier tuple**.
- They resolve it to **different URLs**:
  - sender → mutation-capable surface,
  - receiver → observation-only surface.
- At most one URL is returned per epoch per role.

The receiver **never** resolves mutation-capable URLs.  
The sender **may** resolve observation-only URLs but performs no mutation on them.

---

## Sender–Receiver Temporal Ordering (Enforced)

DeployStega enforces strict ordering:

- **Sender mutation precedes receiver observation** for any artifact resolved in the same epoch.
- Receiver access is delayed by a feasibility-governed minimum latency.

Receiver access may occur:

- later within the same epoch, or
- in a subsequent epoch window,

provided feasibility constraints are satisfied.

---

## Receiver-Side Verification

DeployStega provides **deterministic rendezvous with guaranteed observation**, not best-effort polling.

### Decode Rule

For each resolved artifact:

1. The receiver accesses `URL_receiver`.
2. The receiver scans all candidate content.
3. The receiver attempts steganographic decoding.
4. If decoding succeeds, the payload is accepted.
5. If decoding fails, the artifact is benign.

No acknowledgments, retries, or signaling occur.

---

## Timeline (Asynchronous, No Runtime Coordination)

### Pre-Experiment

- Repository enumerated
- Snapshot frozen
- Feasibility region learned
- Epoch parameters (including `T₀`) agreed out of band

### Experiment Phase

**Sender (independent):**
- resolves `(artifact, URL_sender)` for every epoch
- mutates artifact when and only when instructed

**Receiver (independent):**
- resolves `(artifact, URL_receiver)` for every epoch
- observes artifacts as instructed
- decodes deterministically

---

## Assumptions and Limitations

### Assumptions

- Fixed snapshot.
- Fixed epoch origin `T₀`.
- Accurate feasibility region.
- Mandatory epoch participation.
- No platform failures.

### Limitations

- No protection against endpoint compromise.
- No handling of snapshot-invalidating repository changes.
- No adversarial interference modeling beyond logs.

---

## Summary

DeployStega’s deterministic dead-drop resolver provides **guaranteed capture under mandatory participation**.

By enforcing:
- deterministic epoch resolution,
- mandatory per-epoch interaction,
- strict sender-before-receiver ordering, and
- feasibility-constrained timing,

the system guarantees that **every payload embedded by the sender is observed by the receiver**, so long as both parties follow the protocol exactly.

The resolver provides **structure and certainty**, not reliability heuristics or messaging semantics, enabling rigorous and unambiguous detectability analysis.
