# DeployStega Feature Extractors

This directory defines the **adversarial feature space \(F\)** used by DeployStega
to evaluate covert communication under realistic, log-level observation in
LLM-mediated collaborative platforms (e.g., GitHub).

Each feature extractor corresponds to a **statistically observable property**
that an enterprise-scale adversary could plausibly compute using standard
platform telemetry, including application logs, access logs, and metadata
stores. The feature set is designed to reflect **capability-bounded observation**
rather than idealized or omniscient detection.

The implemented features satisfy the following design constraints:

- **Non-semantic**: No inspection of message payloads or linguistic content  
- **Population-level**: No per-user labeling or deanonymization  
- **Immutable-input**: Feature extractors do not mutate datasets  
- **Capability-bounded**: Only observables obtainable from realistic logging infrastructure  

Together, these extractors instantiate the adversary’s behavioral and routing
capabilities used throughout DeployStega’s indistinguishability evaluation.

---

## Directory Structure

```mermaid
flowchart TD
    features["features/"]

    features --> behavioural["behaviourial/"]
    features --> routing["routing/"]

    behavioural --> freq["frequency.py"]
    behavioural --> revisit["revisit.py"]
    behavioural --> session["session.py"]
    behavioural --> timing["timing.py"]
    behavioural --> transition["transition.py"]
    behavioural --> namespace["namespace_routing.py"]

    routing --> idconc["identifier_concentration.py"]
    routing --> role["role_asymmetry.py"]
    routing --> shared["shared_access.py"]
    routing --> topo["shared_access_topology.py"]
---

## Behavioral Features (`features/behaviourial/`)

Behavioral features characterize **how users interact with the platform over
time**, independent of semantic content. These features constitute the
behavioral component of the adversary’s capability class,
denoted \(F_{\text{behavioral}}\).

---

### `timing.py` — Intra-User Timing (`ft`)

**Extracted quantity**  
The empirical distribution of inter-event time gaps (\(\Delta t\)) between
consecutive actions performed by the same user.

**Rationale**  
Human activity exhibits structured temporal regularities across multiple time
scales. Automated or covert processes frequently introduce abnormal timing
patterns, including excessive regularity or implausible burstiness.

**Adversarial visibility**  
Inter-action timing is directly observable from standard application and audit
logs.

---

### `session.py` — Session Lengths (`fsession`)

**Extracted quantity**  
The distribution of session durations, defined as the elapsed time between the
first and last action within a contiguous activity session.

**Rationale**  
Benign users typically operate in bounded work sessions separated by idle
periods. Synthetic or adversarial traces often violate these session-level
constraints by producing sessions that are unnaturally short, long, or dense.

**Adversarial visibility**  
Session boundaries can be inferred from authentication events and access logs.

---

### `frequency.py` — Artifact-Class Frequency (`ffreq`)

**Extracted quantity**  
The marginal probability distribution over artifact classes accessed
(e.g., issues, pull requests, comments).

**Rationale**  
Benign developers exhibit stable aggregate usage profiles across artifact types.
Routing-based covert communication may bias these proportions, even when
per-user behavior remains superficially plausible.

**Scope limitation**  
This feature captures **aggregate frequencies only** and does not encode
sequential or per-user information.

---

### `transition.py` — Artifact-Class Transitions (`faccess-transition`)

**Extracted quantity**  
An empirical transition matrix describing the probability of accessing artifact
class \(C_j\) immediately after \(C_i\).

**Rationale**  
Developer workflows follow structured navigation patterns (e.g., issue →
pull request → review). Dead-drop routing mechanisms must conform to these
patterns to avoid detection.

**Implementation note**  
Transitions are computed using `event.metadata["artifact_class"]` rather than
`action_type`, reflecting the fact that routing-induced events often share a
uniform action label at the log level.

---

### `revisit.py` — Artifact Revisit Behavior (`frevisit`)

**Extracted quantities**  
For each user (aggregated across users):

- Proportion of actions that revisit previously accessed artifacts  
- Number of distinct artifacts accessed  
- Maximum number of revisits to a single artifact  

**Rationale**  
Dead-drop receivers may repeatedly poll shared artifacts awaiting payload
updates. Elevated revisit rates or extreme concentration on specific artifacts
are strong indicators of routing-based covert channels.

---

### `namespace_routing.py` — Routing Namespace Definition (Support Module)

**Purpose**  
Defines the canonical routing namespace, including:

- Artifact classes  
- Identifier schemas  
- GitHub event-to-artifact mappings  
- Identifier-preserving action constraints  

**Role in the system**  
This module is not itself a feature extractor. Instead, it provides a shared
semantic foundation ensuring that behavioral and routing features operate over a
consistent, immutable interpretation of platform artifacts.

---

## Routing and Access-Topology Features (`features/routing/`)

Routing features capture **structural properties of shared artifact access**
between users, particularly those introduced by dead-drop communication
mechanisms. These features extend \(F_{\text{behavioral}}\) to include routing
observables.

---

### `shared_access.py` — Shared Access Overlap (`fr_shared_access_overlap`)

**Extracted quantities**  

- Number of artifacts accessed by both sender and receiver  
- Size of the union of accessed artifacts  
- Jaccard similarity between access sets  

**Rationale**  
Dead-drop channels necessarily induce shared access. Excessive overlap is
detectable at the access-log level, even in the absence of semantic leakage.

---

### `role_asymmetry.py` — Role Asymmetry (`fr_role_asymmetry`)

**Extracted quantities**  

- Total access counts per role (sender vs. receiver)  
- Total variation distance (TVD) between role-specific access distributions  

**Rationale**  
Benign collaborators typically exhibit stable, asymmetric role behavior.
Routing-based covert communication may induce unnatural symmetry or imbalance.

---

### `shared_access_topology.py` — Shared Access Topology (`fr_shared_access_topology`)

**Extracted quantities**  

- Fraction of shared artifacts  
- Fraction of sender-only artifacts  
- Fraction of receiver-only artifacts  
- Total number of unique artifacts involved  

**Rationale**  
This feature captures the **structural topology** of access patterns, rather than
their frequency, distinguishing natural collaboration from coordinated covert
access.

---

### `identifier_concentration.py` — Identifier Concentration (`fr_identifier_concentration`)

**Extracted quantities**  

- Number of unique artifact identifiers  
- Herfindahl–Hirschman Index (HHI) over artifact accesses  
- Normalized entropy of identifier usage  

**Rationale**  
Dead-drop routing often concentrates activity on a small number of artifacts.
Benign activity tends to be more diffuse. Entropy-based measures are robust,
scale-invariant, and well-established in traffic and anomaly analysis.

---

## Design Rationale

The implemented feature set adheres to the following principles:

- **No payload inspection**: The adversary observes logs, not message content  
- **No user targeting**: Features are aggregated across users  
- **No model assumptions**: Extractors return empirical statistics only  
- **Composability**: Supports behavioral-only, routing-only, and cross-layer
  adversarial evaluations  

These features enable DeployStega’s **differential-privacy–style neighboring
dataset analysis**, in which indistinguishability is evaluated at the population
level.

---

## Summary

Collectively, these feature extractors operationalize the adversary’s capability
class \(F\), encompassing:

- Temporal behavior  
- Session structure  
- Artifact usage frequency  
- Workflow transitions  
- Revisit dynamics  
- Routing topology  
- Role asymmetry  
- Identifier concentration  

Rather than asking whether an individual message appears steganographic,
DeployStega evaluates a stronger and more realistic question:

> *Does the resulting population of platform logs remain statistically
> indistinguishable from benign activity?*

This system-level framing constitutes a central contribution of DeployStega.
