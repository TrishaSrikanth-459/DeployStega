# Deterministic Dead-Drop Resolver

## Purpose

This module specifies the **deterministic dead-drop routing function**
that maps shared cryptographic inputs to a *concrete, existing GitHub
artifact identifier* and a *role-specific URL* at a given epoch `t`.

The resolver guarantees that sender and receiver independently derive
**the same artifact identifier** while resolving it to **different,
role-appropriate URLs** that reflect statistically benign behavior.
Routing is defined structurally, not behaviorally: this module specifies
*what* is referenced, not *when* or *how often* it is accessed.

---

## Scope and Non-Goals

### In Scope
- Deterministic mapping from shared inputs to:
  - a GitHub artifact class
  - an **existing identifier tuple** within a fixed repository snapshot
- Role-specific URL resolution (sender vs. receiver)

### Out of Scope
- Payload encoding or decoding
- Behavioral timing, ordering, or scheduling
- Network access, permissions, or platform responses
- Retransmission, acknowledgment, or delivery guarantees
- Modeling adversarial interference or repository evolution

---

## Fixed Repository Snapshot Assumption

This resolver operates relative to a **fixed repository snapshot**
exchanged out-of-band between sender and receiver prior to the experiment.

The snapshot defines:
- the repository identity (`owner`, `repo`)
- the set of artifact classes considered routable
- the set of **existing identifiers** eligible for routing
- empirically observed identifier bounds and distributions

### Assumption

After snapshot exchange:

- **No external actor mutates the repository** in a way that affects:
  - artifact existence
  - identifier stability
  - namespace structure
- Specifically, no issues, pull requests, commits, discussions, or
  comments referenced by the resolver are deleted, renumbered, edited, or
  transferred during the experiment by an external actor. 

This assumption is adopted to:
- prevent silent message loss due to external interference
- avoid introducing the need for live state queries that would appear in logs
- isolate routing detectability from availability failures

If this assumption is violated in a real deployment, routing correctness
is not guaranteed. This tradeoff is accepted to enable controlled,
measurable detectability experiments.

---

## Inputs

All inputs are agreed upon out-of-band:

- **Epoch `t`**  
  A shared, discrete epoch index.

- **Sender identifier `senderID`**  
  A stable identifier for the sender.

- **Receiver identifier `receiverID`**  
  A stable identifier for the receiver.

- **Repository snapshot configuration**
  - repository owner and name
  - artifact-class namespace `N`
  - list of existing identifiers per class
  - empirical identifier bounds and frequencies

---

## Outputs

At epoch `t`, the resolver outputs:

- an artifact class `C ∈ N`
- a **concrete identifier tuple that exists in the snapshot**
- a **role-specific canonical GitHub URL**

Routing is defined over the tuple:

Route(t, role) = (artifactClass, identifierTuple, URL_role)

---

## Deterministic PRNG Core

### PRNG Selection

The resolver uses a deterministic pseudo-random generator derived from a
cryptographic hash function `H`, chosen for:

- reproducibility
- uniformity over identifier space
- independence across epochs

The PRNG is used **only to select among snapshot-defined possibilities**,
never to invent identifiers.

### PRNG Interface

The shared digest is computed as:

digest = H(t, senderID, receiverID)

All routing decisions are derived from fixed slices of this digest.

---

## Digest-to-Artifact Resolution

### Artifact Class Selection

The first slice of the digest selects an artifact class:

classIndex = int(digest[0:8]) mod |N|
artifactClass = N[classIndex]

This indexing applies **only** to the fixed, agreed-upon class set `N`.

---

### Identifier Selection Within Snapshot

For the selected artifact class:

1. Let `S_C` be the snapshot-defined set of existing identifiers
   for class `C`.
2. The resolver deterministically selects **one identifier from `S_C`**
   using digest-derived values.
3. Selection is stable across sender and receiver.

This guarantees that **every resolved identifier exists** and is
addressable for the duration of the experiment.

---

## Sender vs. Receiver URL Resolution

Although sender and receiver resolve the **same identifier tuple** at
epoch `t`, they intentionally resolve it to **different URLs**.

- The **sender** resolves the identifier to a URL that supports
  *benign mutation* (e.g., create, edit, reply, or update).
- The **receiver** resolves the same identifier to a URL that supports
  *benign observation* (e.g., view, scroll, or read).

This asymmetry is essential: routing agreement occurs at the identifier
level, while **behavioral realism is enforced at the URL level**.

---

## Canonical URL Construction

Identifier tuples are converted into canonical GitHub URLs using fixed,
public templates.

Examples:

- Issues:  
  `https://github.com/{owner}/{repo}/issues/new`
  
- Issue comments:  
  ` https://github.com/{owner}/{repo}/issues/{issue_number}`

- Pull requests:  
  `https://github.com/{owner}/{repo}/pull/{pull_number}`

- Commits:  
  `https://github.com/{owner}/{repo}/edit/{branch}/{path}`

### Behavioral Dependence of URL Selection

The **specific URL chosen** is as important as the identifier itself.
The same identifier may admit multiple valid URLs corresponding to
distinct behaviors (viewing, editing, replying, or creating).

Both sender-side and receiver-side URL selection are constrained by
**statistical distributions of benign behavior** derived from empirical
datasets. Final routing is therefore defined by the pair:

(identifierTuple, URL_role),

not by the identifier alone.

---

## Collision Handling

A collision occurs if a digest-derived selection maps to an identifier
that is invalid or unavailable within the snapshot.

Collisions are resolved deterministically by applying a fixed rehashing
rule until a valid, existing identifier is selected.

---

## Resolver API

The resolver exposes a single pure function:

ResolveDeadDrop(t, senderID, receiverID, role)
→ { artifactClass, identifierTuple, canonicalURL }

