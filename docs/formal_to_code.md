---

## **Transcript (T)**

**Formal definition:**  
 Abstract structured object representing adversarially specified intent.

**Code representation:**  
 Immutable Python `@dataclass` with explicitly typed fields

**Proposed location:**  
 `core/transcript.py`

**Fields:**

* `payload_spec: PayloadSpec`

* `behavioral_spec: BehavioralSpec`

* `routing_spec: RoutingSpec`

**Key invariants enforced in code:**

* No absolute timestamps

* No platform-specific identifiers

* No references to logs, features, or observables

* Serializable and hashable

**Notes:**  
 The transcript is never executed directly. It is only passed to feasibility  
 checking and execution functions.

---

## **Payload Specification**

**Formal definition:**  
 Abstract specification of the covert message content.

**Code representation:**  
 Immutable wrapper around a byte sequence (e.g., `bytes` stored in a dataclass)

**Proposed location:**  
 `core/payload.py`

**Key invariants enforced in code:**

* Contains message content only

* No token positions, probabilities, or execution metadata

* Embedding success or failure is not represented here

**Notes:**  
 Payload logic must not assume where or when embedding occurs.

---

## **Behavioral Specification**

**Formal definition:**  
 Abstract description of intended interaction structure and relative timing.

**Code representation:**  
An immutable struct with three explicit fields: a set of action identifiers, a set of ordered pairs specifying which actions must occur before others, and an ordered list of sessions where each session is a set of action identifiers. 

**Proposed location:**  
 `core/behavioral_spec.py`

**Key invariants enforced in code:**

* Relative ordering only (no timestamps)

* No references to logs or timing features

* No direct mapping to execution time

---

## **Routing Specification**

**Formal definition:**  
 Abstract routing intent over artifact classes and access relationships.

**Code representation:**  
An immutable struct with three explicit fields: a set of artifact class labels, a set of ordered pairs specifying relative access constraints between classes, and an ordered list of access stages where each stage lists the artifact classes accessed at that stage.

**Proposed location:**  
 `core/routing_spec.py`

**Key invariants enforced in code:**

* No concrete artifact identifiers

* No access to routing observables

* Artifact classes only

---

## **Feasibility Region (R)**

**Formal definition:**  
 Set of admissible transcripts learned from benign data.

**Code representation:**  
An immutable Python class storing learned feasibility parameters (e.g., timing bounds, format rules, routing constraints) and exposing method `is_feasible(T)` that returns a boolean.

**Proposed location:**  
 `feasibility/region.py`

**Key invariants enforced in code:**

* Read-only during evaluation

* Deterministic membership decision

* Independent of adversarial choices

---

## **Feasibility Check (Feasible(T))**

**Formal definition:**  
 Boolean-valued function testing transcript admissibility.

**Code representation:**  
Function invoking the feasibility region’s membership test

**Proposed location:**  
 `feasibility/check.py`

**Key invariants enforced in code:**

* No side effects

* Deterministic

* Does not modify T

---

## **Execution Function (Execute(T))**

**Formal definition:**  
 Maps feasible transcripts to executable interaction traces.

**Code representation:**  
 Deterministic function returning an immutable interaction trace object. An interaction trace object is an immutable, ordered list of interaction-event records. An interaction-event record is a struct corresponding to a single, logged user action, consisting of the timestamp, accessed artifact identifiers, action type, and other objects.

**Proposed location:**  
 `execution/execute.py`

**Key invariants enforced in code:**

* Only callable on feasible transcripts

* Produces interaction traces only

* All outputs are observable via capability class F

---

## **Capability Class (F)**

**Formal definition:**  
 Set of feature-extraction functions available to the adversary.

**Code representation:**  
 An immutable dictionary whose keys are unique feature identifiers and whose values are deterministic feature-extraction functions, each of which inputs an interaction trace list and returns a finite set of feature values.”

**Proposed location:**  
 `features/capability.py`

**Key invariants enforced in code:**

* Fixed prior to evaluation

* No access to raw logs outside declared extractors

* Each extractor declares its input scope

---

## **Semantic Feature Set (F\_semantic)**

**Formal definition:**  
 Subset of F extracting linguistic features.

**Code representation:**  
An immutable dictionary obtained by filtering the global capability-class extractor dictionary by a fixed list of semantic feature names.

**Proposed location:**  
 `features/semantic/`

**Key invariants enforced in code:**

* Linguistic inputs only

* No behavioral or routing data

---

## **Behavioral Feature Set (F\_behavioral)**

**Formal definition:**  
 Subset of F extracting behavioral features.

**Code representation:**  
An immutable dictionary obtained by filtering the global capability-class extractor dictionary by a fixed list of behavioral feature names.

**Proposed location:**  
 `features/behavioral/`

**Included extractors:**

* Intra-user timing gaps

* Action frequency statistics

* Temporal correlation structure

* Review latency

* Retrieval latency

**Key invariants enforced in code:**

* No semantic inputs

* No routing topology inputs

---

## **Routing Feature Set (F\_routing)**

**Formal definition:**  
 Subset of F extracting routing and access-topology features.

**Code representation:**  
An immutable dictionary obtained by filtering the global capability-class extractor dictionary by a fixed list of routing feature names.

**Proposed location:**  
 `features/routing/`

**Included extractors:**

* Access topology patterns

**Key invariants enforced in code:**

* Access metadata only

* No semantic or behavioral features

---

## **Dataset (D)**

**Formal definition:**  
 Collection of benign interaction traces.

**Code representation:**  
An immutable ordered list consisting of interaction-trace lists (itself an immutable ordered list of interaction-event structs), representing one user’s full interaction history.

**Proposed location:**  
 `data/benign_dataset.py`

**Key invariants enforced in code:**

* Contains only real benign traces

* No synthetic content

---

## **Neighboring Dataset (D′)**

**Formal definition:**  
 Dataset differing from D by one or k users.

**Code representation:**  
A read-only Python class whose internal state consists of (i) an immutable ordered list of per-user interaction traces representing the benign dataset and (ii) an immutable dictionary mapping selected user indices to replacement interaction traces; dataset access is implemented by index lookup against these two fields.

**Proposed location:**  
 `data/neighboring_dataset.py`

**Key invariants enforced in code:**

* Differs from D only in specified user traces

* Replacement trace generated via `Execute(T)`

---

## **Adversary (A)**

**Formal definition:**  
 Classifier attempting to distinguish D from D′.

**Code representation:**  
 Classifier interface accepting feature sets as input

**Proposed location:**  
 `adversary/classifier.py`

**Key invariants enforced in code:**

* Inputs restricted to features in F

* No access to raw logs

---

## **Indistinguishability Parameter (ε)**

**Formal definition:**  
 Empirical adversarial advantage.

**Code representation:**  
 Single floating-point value computed from classifier statistics

**Proposed location:**  
 `evaluation/epsilon.py`

**Key invariants enforced in code:**

* Computed post-hoc

* Derived only from classifier outputs

---

## **Population Size Parameter (k)**

**Formal definition:**  
 Number of covert users.

**Code representation:**  
 Integer stored in experiment configuration

**Proposed location:**  
 `config/experiment.yaml`

---

## **Dead-Drop Resolution Function (DeadDrop(t))**

**Formal definition:**  
 Deterministic artifact resolution function.

**Code representation:**  
 Pure function mapping `(seed, epoch)` to an artifact identifier tuple

**Proposed location:**  
 `routing/deaddrop.py`

---

## **PRNG Seed (s)**

**Formal definition:**  
 Shared secret seed.

**Code representation:**  
 Byte string loaded from secure configuration

**Proposed location:**  
 `config/secrets.yaml` (not committed)

---

## **Epoch Schedule (t)**

**Formal definition:**  
 Discrete time index.

**Code representation:**  
 Monotonic integer counter or iterator

**Proposed location:**  
 `routing/epoch.py`

---

## **Feature Extractors**

**Formal definition:**  
 Functions mapping interaction traces to feature values.

**Code representation:**  
 Callable objects with declared input scope and output schema

**Proposed location:**  
 `features/`

---

## **Adversarial Classifiers**

**Formal definition:**  
 Binary classifiers trained by the adversary.

**Code representation:**  
 External or internal ML models conforming to the classifier interface

**Proposed location:**  
 `adversary/models/`

---

