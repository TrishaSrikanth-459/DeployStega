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
- the **steganographic encoding algorithm** (to the sender),
- the **steganographic decoding key** (to the receiver),
- the **epoch definition**, including:
  - epoch duration,
  - a **fixed epoch origin time `T₀`**,
  - epoch inspection window size `W`.

The following items are **not shared out of band**:

- the steganographic payload itself,
- which epochs contain payloads,
- which artifacts carry payloads,
- whether any given epoch contains a payload at all.

DeployStega does **not** attempt to conceal out-of-band setup assumptions.  
These are assumed to be exchanged privately and are **outside the threat model**.

---

## Epoch Definition (Critical Clarification)

### Logical Epochs

An **epoch** is a logical index defined as:

t = floor((current_unix_time − T₀) / epoch_duration_seconds)

where:

- **`T₀`** is a fixed Unix timestamp agreed upon out of band,
- **`epoch_duration_seconds`** is fixed for the experiment,
- **`current_unix_time`** is obtained locally at runtime.

Epochs are **indices, not events**.

- They do not imply that a sender posted.
- They do not imply that a receiver read.
- They exist solely to parameterize deterministic resolution.

Epoch counting begins at the fixed origin time `T₀`.  
Running any script does **not** reset epoch counting.

---

### Mandatory Epoch Participation

For the duration of the experiment:

- **Every url outputted at every epoch is evaluated by both sender and receiver**.
- If the feasibility region yields **no admissible URL** for a role at epoch `t`,
  that role performs **no routing action** for that epoch.
- Otherwise, the role performs **exactly one interaction attempt** derived from the resolver output.

Participants do **not** choose which epochs to visit; they are required to follow the resolver's instructions exactly. 
Further, participants are not allowed to visit any urls associated with the GitHub repo outside the provided urls for that epoch.

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

If the resolver outputs a URL, that URL is **guaranteed valid on GitHub**.

---

## Behavioral Feasibility Region

The behavioral feasibility region constrains admissible tuples of the form:

(epoch_window, artifactClass, role, URL)

The resolver **never emits URLs outside this region**.

The feasibility region will take into account the timing between the sender's edits and the receiver's capture to minimize detectability. 

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

For each `(t, role)`, the resolver outputs exactly one triple:

(artifactClass, identifierTuple, URL_role)

All outputs are:

- snapshot-valid,
- behaviorally feasible,
- deterministic.

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
- Exactly one URL is returned per epoch per role.

The receiver never resolves mutation-capable URLs.  
The sender may resolve observation-only URLs but performs no mutation on them.

---

## Sender–Receiver Temporal Ordering (Explicit)

DeployStega enforces the following ordering constraint:

- **Sender interactions occur before receiver observations** for the same epoch-resolved artifact.
- The receiver does **not** attempt to read an artifact concurrently with the sender’s mutation.

The minimum delay between sender mutation and receiver observation is governed by the behavioral feasibility region and reflects empirically observed benign retrieval latencies.

If required, receiver observation may occur **later within the same epoch or in a subsequent epoch window**, provided it remains feasible.

---

## Receiver-Side Verification Without Coordination

DeployStega provides **verifiable rendezvous candidates**, not delivery guarantees.

### Decode-or-Discard Rule

For each resolved artifact:

1. The receiver accesses the artifact via `URL_receiver`.
2. The receiver extracts candidate content.
3. The receiver attempts steganographic decoding.
4. If decoding fails, the artifact is treated as benign.
5. If decoding succeeds, the payload is accepted.

No acknowledgments, retries, or feedback occur.

---

## Receiver Epoch Inspection Window

At logical time `T`, the receiver inspects epochs:

t ∈ [T − W, T]

where:

- `W` is fixed for the experiment,
- each epoch yields at most one observation URL,
- epochs outside the window are never inspected.

The receiver terminates inspection upon the **first successful decode**.

---

## Eventual Observability (Conditional)

DeployStega does **not** guarantee delivery.

It guarantees **eventual observability under a bounded search policy**, provided that:

- the sender performs a valid mutation in some epoch,
- the artifact persists,
- the receiver inspects that epoch within its window,
- decoding succeeds.

This is a **bounded search problem**, not a messaging protocol.

---

## Timeline (Asynchronous, No Runtime Coordination)

### Pre-Experiment

- Repository enumerated
- Snapshot frozen
- Feasibility region learned
- Epoch parameters (including `T₀`) agreed out of band

### Experiment Phase

**Sender (independent):**
- resolves `(artifact, URL_sender)` for each epoch
- mutates artifact at a feasibility-permitted time

**Receiver (independent):**
- resolves `(artifact, URL_receiver)` for epochs in `[T − W, T]`
- inspects artifacts
- stops upon successful decode

---

## Receiver-Side Comment Scanning (Design Clarification)

For comment-bearing artifact classes, the resolver routes to the **container-level URL** (issue, pull request, or commit page).

Consequently:

- The sender mutates **one specific comment**.
- The receiver scans **all visible comments** and applies decoding.
- This ambiguity is intentional and reflects GitHub’s UI constraints.

Receiver-side scanning is a **bounded search cost traded for stealth**, not a routing defect.

---

## Assumptions and Limitations

### Assumptions

- Fixed snapshot.
- Fixed epoch origin `T₀`.
- Accurate feasibility region.
- Sender and receiver are collaborators.
- Private out-of-band setup.

### Limitations

- No delivery guarantees.
- No repository evolution handling.
- No adversarial interference modeling.
- No traffic shaping beyond feasibility constraints.

---

## Summary

DeployStega’s deterministic dead-drop resolver enforces **structure without coordination**.

By mandating epoch participation, enforcing sender-before-receiver ordering, and delegating plausibility to a feasibility region, the resolver enables **verifiable covert rendezvous** suitable for rigorous detectability analysis — not messaging guarantees.
