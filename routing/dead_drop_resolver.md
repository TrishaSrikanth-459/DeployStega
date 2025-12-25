# Deterministic Dead-Drop Resolver

## Purpose

This module specifies the **deterministic resolution mechanism** that maps a shared cryptographic digest to a concrete, addressable GitHub artifact identifier at a given epoch. Its sole purpose is to ensure that both sender and receiver independently compute the *same artifact reference* using shared inputs, without coordination, feedback, or state. The resolver operates strictly at the level of namespace structure and identifier construction, and explicitly excludes payload encoding, behavioral modeling, timing control, access execution, or observation logic.

---

## Scope and Non-Goals

### In Scope
- Deterministic mapping from a shared digest to:
  - a GitHub artifact class
  - a valid identifier tuple within that class
- Enforcement of artifact-specific identifier formats
- Canonical GitHub URL construction from identifiers
- Deterministic handling of collisions and invalid identifiers
- Structural plausibility guarantees (existence, format, stability)

### Out of Scope
- Payload encoding or decoding
- Behavioral timing, jitter, batching, or scheduling
- Network access, authentication, or permission checks
- Artifact creation, mutation, or deletion
- Retransmission, acknowledgment, or delivery guarantees
- Any form of adaptive or stateful routing logic

---

## Inputs

The resolver requires the following inputs:

- **Epoch value `t`**  
  A shared, discrete time index agreed upon out-of-band.

- **Sender identifier `senderID`**  
  A stable identifier for the sender account.

- **Receiver identifier `receiverID`**  
  A stable identifier for the receiver account.

- **Shared repository identifier `repoId`**  
  A fixed configuration parameter identifying the collaborative repository.
  This value is *not* derived from the digest.

- **Routing namespace `N`**  
  An ordered set of GitHub artifact classes shared by sender and receiver.

- **Per-class bounds**  
  Upper bounds `MaxFₖ(repoId)` for each numeric identifier field required by
  an artifact class, derived from empirical metadata.

---

## Outputs

The resolver outputs:

- **Artifact class `C ∈ N`**
- **Identifier tuple** matching the schema of `C`
- **Canonical GitHub URL** corresponding to the identifier tuple

The output uniquely specifies a single GitHub artifact reference for epoch `t`.

---

## Deterministic PRNG Core

### PRNG Selection

The resolver uses a **cryptographic hash function** `H` as its deterministic
pseudo-random generator. A cryptographic hash is chosen to ensure:
- uniform distribution over the namespace
- resistance to bias or correlation
- deterministic reproducibility across parties

### PRNG Interface

The PRNG interface is defined as:

digest = H(t, senderID, receiverID)

yaml
Copy code

The output `digest` is a fixed-length byte string. All subsequent resolution
steps operate exclusively on slices of this digest.

---

## Digest-to-Artifact Resolution

### Artifact Class Selection

Artifact class selection uses the first 8 bytes of the digest:

index = int(digest[0:8]) mod |N|
artifactClass = N[index]

python
Copy code

This selects a class uniformly from the routing namespace. Importantly, this
index selects **only the artifact class**, not the repository.

### Identifier Field Allocation

The remaining digest bytes are partitioned into fixed slices:

primary = int(digest[8:16])
secondary = int(digest[16:24])
tertiary = int(digest[24:32])

vbnet
Copy code

These slices are mapped to identifier fields depending on the arity of the
selected artifact class:

- **One field**:
f1 = (primary mod MaxF1(repoId)) + 1

markdown
Copy code
- **Two fields**:
f1 = (primary mod MaxF1(repoId)) + 1
f2 = (secondary mod MaxF2(repoId)) + 1

markdown
Copy code
- **Three fields**:
f1 = (primary mod MaxF1(repoId)) + 1
f2 = (secondary mod MaxF2(repoId)) + 1
f3 = (tertiary mod MaxF3(repoId)) + 1

yaml
Copy code

The final identifier tuple prepends the fixed `repoId`.

### Identifier Constraints

All identifiers must:
- conform to the schema defined in `identifier_schemas.md`
- lie within empirically observed bounds
- respect GitHub’s identifier typing (numeric IDs or commit SHAs)

Identifiers failing these constraints are treated as invalid.

---

## Canonical URL Construction

Each identifier tuple is converted into a **canonical GitHub web URL**
using fixed, publicly documented URL templates.

Examples:
- Issues:  
`https://github.com/{owner}/{repo}/issues/{issueNumber}`
- Issue comments:  
`https://github.com/{owner}/{repo}/issues/{issueNumber}#issuecomment-{commentId}`
- Pull requests:  
`https://github.com/{owner}/{repo}/pull/{prNumber}`
- Commits:  
`https://github.com/{owner}/{repo}/commit/{commitSha}`
- Discussion comments:  
`https://github.com/{owner}/{repo}/discussions/{discussionNumber}?commentId={commentId}`

URL construction is purely syntactic and does not perform resolution.

---

## Collision Handling

### Collision Definition

A collision occurs when:
- two distinct epochs resolve to the same `(artifactClass, identifier tuple)`
under identical repository configuration.

### Collision Resolution Strategy

Collisions are handled deterministically by:
- incorporating epoch `t` into the hash input, and
- relying on the cryptographic hash’s avalanche properties.

No state, memory, or coordination is used to resolve collisions.

---

## Invalid Identifier Handling

If an identifier tuple fails validation (e.g., out of bounds):
- the resolver advances deterministically to the next digest slice
(or re-hashes with a fixed salt)
- the resolution process repeats until a valid identifier is produced

This procedure is deterministic and identical for sender and receiver.

---

## Resolver API

The resolver exposes a single pure function:

ResolveDeadDrop(t, senderID, receiverID, repoId) → {
artifactClass,
identifierTuple,
canonicalURL
}

yaml
Copy code

The function is stateless and side-effect free.

---

## Determinism Guarantees

The resolver guarantees that:
- identical inputs always produce identical outputs
- no external state influences resolution
- resolution is independent of network conditions, permissions, or timing

Determinism holds across executions, machines, and parties.

---

## Routing Correctness Tests

Correctness is verified by:
- replay tests over fixed `(t, senderID, receiverID)` tuples
- cross-party consistency checks
- schema validation against `identifier_schemas.md`
- bounds checking using `prevalence_table.md`

---

## Plausibility Checks (Structural Only)

Plausibility is evaluated by ensuring:
- all artifact classes appear in the benign dataset `D`
- identifier formats match those observed in GitHub APIs
- identifier ranges are empirically grounded

No behavioral or temporal plausibility is assessed here.

---

## Assumptions and Limitations

**Assumptions**
- Sender and receiver share inputs out-of-band
- Repository configuration is fixed
- Permissions and network conditions are ideal
- Namespace and schemas are consistent across parties

**Limitations**
- No delivery guarantees
- No adaptation to repository evolution
- No detection or correction of access failures
- No payload awareness

---

## Summary

The deterministic dead-drop resolver provides a reproducible, stateless mapping
from shared cryptographic inputs to concrete GitHub artifact references. It
guarantees consistency, structural validity, and plausibility within the routing
namespace, while deliberately excluding behavior, access, timing, and payload
semantics. As such, it forms the core structural routing primitive upon which
higher-layer encoding and observation mechanisms may safely operate.
