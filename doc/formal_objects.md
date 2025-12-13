# Formal Object Inventory for DeployStega

This document enumerates all formal objects used in the DeployStega system
and security definitions. Every object listed here corresponds to a
well-defined entity referenced in the paper and is required to have
unambiguous semantics in both the theoretical model and implementation.

For each object, we specify its type, role in the security experiment,
and whether it is chosen by the adversary, fixed by the model, or derived
algorithmically.

---

## Transcript (T)

**Type:** Abstract structured object

**Defined in paper as:**  
A covert transcript representing an intended pattern of covert communication,
consisting of a payload specification, a behavioral specification, and a
routing specification.

**Role in security experiment:**  
Represents adversarial intent. The transcript is subjected to a feasibility
check; if feasible, it is executed to produce a synthetic interaction trace
that replaces a benign user’s log in the neighboring dataset.

**Chosen by:**  
Adversary

**Notes / Invariants:**  
- Contains no absolute timestamps  
- Contains no platform-specific identifiers  
- Does not directly reference logs, features, or observables  

---

## Payload Specification

**Type:** Component of Transcript

**Defined in paper as:**  
The bitstring to be embedded and its embedding schedule.

**Role in security experiment:**  
Defines the covert information content to be hidden within linguistic output.

**Chosen by:**  
Adversary

**Notes / Invariants:**  
- Payload embedding may be skipped or delayed if feasibility constraints
  prevent embedding at a given step  

---

## Behavioral Specification

**Type:** Component of Transcript

**Defined in paper as:**  
A sequence of user actions and session structure describing intended timing
and interaction patterns.

**Role in security experiment:**  
Constrains how covert communication is embedded into user behavior and
determines interaction timing subject to feasibility constraints.

**Chosen by:**  
Adversary (subject to feasibility)

---

## Routing Specification

**Type:** Component of Transcript

**Defined in paper as:**  
A plan describing which application artifacts are accessed and at what
relative times.

**Role in security experiment:**  
Defines the intended routing of covert communication through shared
application artifacts.

**Chosen by:**  
Adversary (subject to feasibility)

---

## Feasibility Region (𝓡)

**Type:** Set of valid transcripts

**Defined in paper as:**  
The set of transcripts that satisfy empirically learned timing, message-format,
and routing constraints derived from benign platform traces.

**Role in security experiment:**  
Defines admissible adversarial behavior. Only transcripts T ∈ 𝓡 may be
executed; transcripts outside 𝓡 are rejected.

**Chosen by:**  
Model (learned from benign data)

**Notes / Invariants:**  
- Fixed prior to evaluation  
- Deterministic membership test  
- Independent of adversarial choices  

---

## Feasibility Predicate (Feasible(T))

**Type:** Boolean-valued function

**Defined in paper as:**  
A deterministic feasibility check returning true if T ∈ 𝓡 and false otherwise.

**Role in security experiment:**  
Determines whether an adversarially chosen transcript is admissible.

**Chosen by:**  
Model

---

## Execution Function (Execute(T))

**Type:** Deterministic transformation

**Defined in paper as:**  
A function that maps a feasible transcript T ∈ 𝓡 to an executable interaction
trace consistent with benign platform behavior.

**Role in security experiment:**  
Produces the synthetic interaction log that replaces a benign user’s log in
the neighboring dataset D′.

**Chosen by:**  
Model

**Notes / Invariants:**  
- Only defined for T ∈ 𝓡  
- Produces observables restricted to capability class F  

---

## Capability Class (F)

**Type:** Set of feature extraction functions

**Defined in paper as:**  
The set of semantic, behavioral, and routing observables extractable from
platform logs by the adversary.

**Role in security experiment:**  
Defines the adversary’s observational power and the input space for
adversarial classifiers.

**Chosen by:**  
Model (threat model assumption)

---

## Semantic Feature Set (F_semantic)

**Type:** Subset of Capability Class

**Defined in paper as:**  
Token-level linguistic features including KL divergence, perplexity,
semantic coherence, next-token distributions, and embedding distortions.

**Role in security experiment:**  
Captures detectability arising from linguistic steganography.

**Chosen by:**  
Model

---

## Behavioral Feature Set (F_behavioral)

**Type:** Subset of Capability Class

**Defined in paper as:**  
Application-level interaction features derived from system logs, including
timing gaps, action frequencies, correlation structure, review latency,
retrieval latency, and access topology.

**Role in security experiment:**  
Captures detectability arising from user behavior and interaction patterns.

**Chosen by:**  
Model

---

## Routing Feature Set

**Type:** Subset of Capability Class

**Defined in paper as:**  
Observables derived from artifact access patterns and sender–receiver
unlinkability signals.

**Role in security experiment:**  
Captures detectability arising from routing behavior.

**Chosen by:**  
Model

---

## Dataset (D)

**Type:** Finite collection of interaction traces

**Defined in paper as:**  
A dataset of benign user interaction logs drawn from a real LLM-mediated
application environment.

**Role in security experiment:**  
Serves as the baseline dataset for indistinguishability testing.

**Chosen by:**  
Model (constructed from benign data sources)

---

## Neighboring Dataset (D′)

**Type:** Finite collection of interaction traces

**Defined in paper as:**  
A dataset identical to D except that exactly one (or k) user’s interaction
trace is replaced with a synthetic trace generated by DeployStega.

**Role in security experiment:**  
Used to test whether the presence of covert communication is detectable.

**Chosen by:**  
Model (replacement construction), adversary indirectly via choice of T

---

## Adversary (𝒜)

**Type:** Algorithmic distinguisher

**Defined in paper as:**  
An entity that observes features in capability class F and attempts to
distinguish between datasets D and D′.

**Role in security experiment:**  
Attempts to detect the presence of covert communication.

**Chosen by:**  
Quantified over all classifiers restricted to capability class F

---

## Indistinguishability Parameter (ε)

**Type:** Real-valued scalar

**Defined in paper as:**  
An empirical measure of adversarial advantage computed as
ε = ln(TPR / FPR).

**Role in security experiment:**  
Quantifies the detectability of covert communication under capability class F.

**Chosen by:**  
Computed by the model during evaluation

---

## Population Size Parameter (k)

**Type:** Integer

**Defined in paper as:**  
The number of users replaced with covert users in population-level
indistinguishability experiments.

**Role in security experiment:**  
Controls the density of covert users in dataset D(k).

**Chosen by:**  
Model (experiment parameter)

---

## Dead-Drop Resolution Function (DeadDrop(t))

**Type:** Deterministic mapping

**Defined in paper as:**  
A function mapping a shared PRNG seed and epoch index to a specific application
artifact used for routing covert communication.

**Role in security experiment:**  
Implements application-layer routing indistinguishable from benign access.

**Chosen by:**  
Model (given shared seed)

---

## PRNG Seed (s)

**Type:** Bitstring

**Defined in paper as:**  
A shared seed used by sender and receiver to synchronize dead-drop resolution.

**Role in security experiment:**  
Enables deterministic artifact selection without direct coordination.

**Chosen by:**  
Out-of-band assumption (fixed prior to experiment)

---

## Epoch Schedule (t)

**Type:** Discrete time index

**Defined in paper as:**  
A shared epoch counter used to index dead-drop resolution.

**Role in security experiment:**  
Coordinates routing decisions over time.

**Chosen by:**  
Out-of-band assumption

---

## Feature Extractors

**Type:** Deterministic functions

**Defined in paper as:**  
Procedures that map interaction traces to feature vectors in capability
class F.

**Role in security experiment:**  
Provide the inputs to adversarial classifiers.

**Chosen by:**  
Model

---

## Adversarial Classifiers

**Type:** Binary classification algorithms

**Defined in paper as:**  
Classifiers trained to distinguish between feature vectors derived from D
and D′.

**Role in security experiment:**  
Operationalize detectability and define empirical ε.

**Chosen by:**  
Quantified over all classifiers restricted to F

---
