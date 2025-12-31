# Deterministic Dead-Drop Resolver

## Purpose

This document specifies the **deterministic dead-drop routing function** used by **DeployStega**.

The resolver maps **shared cryptographic inputs** and a **pre-established experimental environment** to:

- a concrete **GitHub artifact class**,
- an **existing, snapshot-validated identifier tuple**, and
- a **single, role-appropriate, behaviorally feasible GitHub URL**,

at a logical epoch index `t`.

The resolver guarantees that for any fixed epoch index t, the sender and receiver independently derive:
- the same artifact identifier tuple, and
- different role-appropriate interaction surfaces (mutation vs. observation).
without runtime communication, acknowledgments, or feedback.

If sender and receiver evaluate different epoch indices, no agreement is expected.

The resolver is a **pure deterministic function** evaluated under externally supplied feasibility constraints.

---

## What Is Shared Out-of-Band

DeployStega **requires** a limited, well-defined set of out-of-band agreements established **before** the experiment.

The following items **are shared out of band**:

- the **repository snapshot**,
- the **dead-drop resolver algorithm**,
- the **steganographic encoding algorithm** (to the sender)
- The **steganographic decoding key** (to the receiver)
- the **epoch definition**, including:
  - epoch duration (e.g., 3 minutes),
  - epoch origin time `T₀`,
  - epoch inspection window size `W`.

The following items are **not shared out of band**:

- the steganographic payload itself,
- when the sender will post,
- which artifact will carry a payload,
- which epoch contains a payload,
- whether any given epoch contains a payload at all.

This separation is essential:
DeployStega does not attempt to conceal out-of-band setup assumptions, which are assumed to be exchanged privately and are outside the threat model.

---

## Epoch Definition (Critical Clarification)

### Logical Epochs

An **epoch** is a logical index defined as:

t = floor((current_time − T₀) / epoch_duration)

- `T₀` is a fixed, agreed-upon start time.
- `epoch_duration` is fixed for the experiment.
- No live messages between the sender and receiver are exchanged at runtime.
- Clock drift tolerance is absorbed by the receiver’s inspection window.

Epochs are **indices**, not events.

---

## Fixed Repository Snapshot Assumption

The resolver operates relative to a **fixed repository snapshot** established **prior to the experiment**.

### Snapshot Properties

The snapshot defines:

- repository identity `(owner, repo)`,
- the routing namespace `N` (artifact classes),
- the complete set of **existing artifact identifiers per class**,
- stable identifier schemas,
- empirically observed identifier bounds.

### Hard Snapshot Validity Rule

The resolver **never outputs invalid or non-addressable URLs**.

Therefore:

- artifact classes with zero valid identifiers are excluded,
- commit identifiers must include concrete `branch` and `path`,
- placeholder identifiers (e.g., `"unknown"`) are forbidden.

If the resolver outputs a URL, that URL is **guaranteed valid on GitHub**.

---

## Behavioral Feasibility Region

The behavioral feasibility region is learned independently from benign GitHub interaction traces.

It constrains admissible tuples:

- `(epoch_window, artifactClass, role, URL)`

The resolver never emits URLs outside this region.

---

## Resolver Inputs (Runtime)

At runtime, each party independently provides:

- epoch index `t`,
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

## Resolver Leverages Deterministic PRNG 

A cryptographic hash function `H` is used as a deterministic PRNG.

digest = H(t || senderID || receiverID)

All selection decisions derive from fixed slices of this digest.

The PRNG **never invents identifiers** — it indexes only from snapshot-defined artifacts.

---

## Sender vs. Receiver Resolution

- Sender and receiver resolve the **same identifier tuple**.
- They resolve it to **different URLs**:
  - sender → mutation-capable surface,
  - receiver → observation-only surface.
- Exactly one URL is returned per epoch to the user.

---

## Receiver-Side Verification Without Coordination

DeployStega does **not** guarantee that the receiver observes the artifact at the exact moment the sender mutates it.

Instead, it provides **verifiable rendezvous candidates**.

### Decode-or-Discard Rule

For each resolved candidate artifact:

1. The receiver accesses the artifact via `URL_receiver`.
2. The receiver extracts a candidate payload.
3. The receiver attempts steganographic decoding.
4. If decoding produces unintelligible text, the artifact is treated as benign.
5. If decoding produces a legigible message, the payload is accepted as the sender’s message.

No acknowledgments, retries, or signaling occur.

---

## Receiver Epoch Inspection Window

The receiver may inspect a **finite window of past epochs**.

At logical time `T`, the receiver evaluates epochs:

t ∈ [T − W, T]

where:

- `W` is a fixed experiment-defined constant (e.g., 20 epochs),
- each epoch yields exactly one observation-only URL,
- epochs outside this window are never inspected.

The receiver terminates inspection upon the **first successful decode**.

---

## Eventual Observability (Conditional)

DeployStega does **not** guarantee delivery.

It guarantees **eventual observability under a bounded search policy**, provided that:

- the sender performs a valid mutation in some epoch `t`,
- the artifact persists,
- the receiver inspects epoch `t` within its inspection window,
- steganographic decoding succeeds.

This is a **search problem with a definitive stopping condition**, not a messaging protocol.

---

## Timeline (Asynchronous, No Runtime Coordination)

### Pre-Experiment (Offline)

- GitHub token provided
- Repository enumerated
- Snapshot frozen
- Feasibility region learned
- Epoch parameters agreed

### Experiment Phase

**Sender (independent):**
- resolves `(artifact, URL_sender)` for epoch `t`
- mutates artifact at any time during epoch `t`

**Receiver (independent):**
- resolves `(artifact, URL_receiver)` for epochs `[T − W, T]`
- inspects artifacts
- stops upon successful decode

---

## Assumptions and Limitations

### Assumptions

- Fixed snapshot.
- Accurate feasibility region.
- Sender and receiver are collaborators.
- Private out-of-band setup.

### Limitations

- No delivery guarantees.
- No repository evolution handling.
- No adversarial interference modeling.
- No traffic shaping or scheduling.

---

## Summary

DeployStega’s deterministic dead-drop resolver enables **verifiable covert rendezvous**, not messaging.

By separating:

- structure (snapshot),
- plausibility (feasibility),
- resolution (pure function),
- verification (cryptographic decode),

the system enables **honest, rigorous detectability analysis** without claiming impossible guarantees or hiding coordination under the rug.
