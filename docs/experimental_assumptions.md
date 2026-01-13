# Experimental Assumptions

This document enumerates the assumptions under which DeployStega
experiments are defined, executed, and evaluated. These assumptions
are explicit, intentional, and necessary to isolate platform-level
detectability from uncontrolled social or organizational factors.

---

## Sender and Receiver Interaction Roles (with Initial Permission Assumptions)
The routing namespace enumerates addressable artifact classes independent
of actor role.

We distinguish between two interaction roles:

- **Sender**: an account capable of creating, modifying, or deleting
  artifacts in order to encode information.
- **Receiver**: an account that accesses existing artifacts through
  standard, read-only interactions in order to observe information.

### Initial Permission Assumption (Explicit)
At experiment start, **both sender and receiver are assumed to be legitimate,
non-admin collaborators** on the same repository, with the following minimum
permissions:

- **Sender permissions (write-level collaborator)**  
  The sender has sufficient permissions to:
  - create and edit issue comments
  - Create and edit pull request comments
  - create and edit commit comments
  - view issues, pull requests, commits, and associated comments
    via standard web URLs   
  - etc.

  The sender is **not** assumed to have repository administrator,
  organization owner, or policy-management privileges.

- **Receiver permissions (read-level collaborator)**  
  The receiver has sufficient permissions to:
  - view the repository
  - view issues, pull requests, commits, and associated comments
    via standard web URLs  

  The receiver is **not** assumed to have write or administrative privileges.
  That they may possess write privileges does not, however, pose any problems.

Sender and receiver interactions need not use identical API endpoints
or HTTP methods. Routing semantics depend on shared artifact identifiers,
not on the specific API endpoints, permissions, or HTTP verbs used to access them.

API- or web-based actions are treated equivalently so long as they preserve
the artifact’s identifier as defined in this routing namespace.

**All sender actions explicitly enumerated in the Addressability (Sender)
sections are assumed to be identifier-preserving by construction.**
These actions may modify artifact content (e.g., editing comments, issue, or pull requests) 
but do not alter any identifier-defining fields specified in this routing namespace.

---

## Access-Control Considerations
Identifier definitions are independent of permissions such that they specify
**how artifacts are named**, not **who can access or modify them**, and are
assumed to remain stable for the duration of the experiment.

### Experimental Assumption (Permissions and Identifier Stability)
For the scope of the DeployStega experiments, **sender, receiver, and all other
collaborators are assumed to retain their initial permissions for the duration
of the experiment**, and:

- All sender-side mutations and receiver-side observations are assumed
  to be authorized when attempted, and are further assumed to be
  **identifier-preserving**.
- **No actor (including the sender, receiver, or the adversary)**
  is assumed to perform actions that would change identifier-defining fields
  as specified in this routing namespace.

In real shared repositories, identifier-changing actions (e.g., repository
renames, issue transfers, history rewriting) may occur due to administrative
decisions or external collaborators. Such events are treated as
**out-of-scope conditions** for the routing model. If an identifier-changing
operation were to occur during an experiment, the run would be considered
**invalidated**, rather than modeled as a routing failure.

---

## Access Failure Handling
Access attempts (sender write-side or receiver read-side) may, in real-world
deployments, fail due to network conditions, platform outages, or policy changes.

### Experimental Assumption (Network and Platform Stability)

For the purposes of the DeployStega experiments, **network connectivity and
GitHub platform availability are assumed to be stable**:
- No adversarial or systematic network failures are injected.
- No GitHub-wide outages or availability disruptions are modeled.
- All attempted accesses are assumed to reach the platform successfully.

This assumption is necessary to focus evaluation on **routing feasibility
and detectability**, rather than on external reliability engineering concerns
that are unrelated to covert signaling structure.

### Consequence
Under this assumption:
- All sender-side actions are assumed to execute successfully.
- All receiver-side accesses are assumed to resolve successfully.

This does **not** imply that DeployStega guarantees delivery in practice,
only that delivery failures arising from permissions or network instability
are explicitly excluded from the experimental scope.

### Justification for No Retransmission or Feedback
Even under idealized access conditions, DeployStega does not assume
retransmission or feedback.

Reliable delivery would require the sender to infer receiver observation
or to receive explicit acknowledgment, introducing detectable coordination,
behavioral coupling, or an out-of-band signaling channel. Such mechanisms
are incompatible with the benign-behavior constraints and feasible-access
logs that govern our routing model.

Accordingly, DeployStega models routing as a **best-effort covert channel**
even under ideal conditions. Reliability, if required, must arise from
encoding redundancy or higher-level protocols outside the routing namespace
itself.

---

## Access Mechanisms
The sender and receiver are modeled as accessing artifacts exclusively
through standard, user-facing GitHub web URLs
(e.g., `https://github.com/{owner}/{repo}`), as would occur during routine
browsing activity.

The model does not assume programmatic access via the GitHub REST or
GraphQL APIs, nor the use of scripted clients.

---

## Experimental Assumption (Collaborator Stability)

For the duration of each DeployStega experiment, **no pending invitations are accepted mid-experiment**, and **the only collaborators present throughout the experiment are the sender and the receiver**.

This assumption ensures that:

- **All observed platform activity arises solely from the sender and receiver**, ensuring that the replacement of a single benign user log with a covert user log is well-defined and controlled.
- **Sender-side actions do not trigger social reactions from external third parties** that would introduce unmodeled behavioral signals, secondary communication channels, or confounding activity traces unrelated to the covert protocol itself.

Examples of excluded third-party social reactions include (but are not limited to):

- A third-party collaborator receiving notifications generated by a sender-authored comment or edit,
- A third-party collaborator replying to, questioning, or expanding upon sender-authored content,
- A third-party collaborator editing, correcting, or rephrasing sender-authored material,
- A third-party collaborator referencing sender activity in a follow-up issue, pull request, or review,
- Off-platform communication (e.g., Slack, email, ticketing systems) triggered by sender actions,
- Cascading interaction effects such as additional comments, reviews, or commits prompted by sender edits.

In real-world organizational repositories, it is common for repositories to include many collaborators, and for social responses to occur as a natural consequence of routine activity. Modeling such reactions would require explicit assumptions about human behavior, notification handling, response latency, and off-platform communication—factors that lie outside the scope of platform-level logging and cannot be reliably inferred from GitHub audit data alone.

---

## Editorial Constraint (Sender)

**The sender is explicitly forbidden from editing artifact titles** (e.g., issue titles, pull request titles, release titles, label names).  
This restriction is imposed because title modifications are **high-salience, globally visible changes** that are **conspicuous** relative to routine collaborative behavior. Such edits introduce disproportionate visibility, rendering them unsuitable for covert signaling under benign-behavior constraints.

Accordingly, all sender-side mutations modeled in this routing namespace are restricted to **non-title content fields** (e.g., bodies, descriptions, comments).

---

## Repository Visibility Assumption (Public vs. Private)

DeployStega’s threat model is **agnostic to repository visibility** (public or private).  
Detectability is evaluated relative to an adversary with access to **enterprise-level platform logs and metadata**, rather than mere public observers or casual repository viewers.

Accordingly:
- Detectability is defined solely with respect to features extractable from centralized security monitoring infrastructure.
- Whether a repository is public or private does not materially affect the evaluated feature space.

This abstraction reflects realistic enterprise security monitoring, where internal logging visibility is independent of repository publicity.

---

## Baseline Repository State and Measurement Window

Detectability is evaluated **only over activity occurring during the experiment window**, beginning at the epoch origin time.

All repository features that exist prior to experiment start, including:
- existing issues, pull requests, comments, and commits,
- repository age, structure, and historical activity,
are **fixed background context** that the adversary does not evaluate as detectability signals. 

According to our differential-privacy formulation, detectability is measured with respect to **incremental deviations** introduced by a single user’s behavior.

---

## Experimental Assumption (Collaborator Stability)

For the duration of each DeployStega experiment, no pending invitations are accepted mid-experiment, and  
**the only collaborators present throughout the experiment are the sender and the receiver.**

This assumption ensures that:
- All observed activity arises solely from the sender and receiver.
- Sender interactions do not elicit social reactions from external third parties that may introduce unmodeled behavioral signals, secondary communication channels, or confounding activity traces.

Examples of excluded social reactions include (but are not limited to):
- A third party receiving notifications triggered by sender-authored comments or edits,
- Replies, questions, or follow-up discussions initiated by external collaborators,
- Edits, corrections, or rephrasings of sender-authored content by others,
- References to sender activity in subsequent issues, pull requests, or reviews,
- Off-platform communication (e.g., Slack or email) triggered by sender actions,
- Cascading interaction effects such as additional comments, reviews, or commits prompted by sender edits.

In real-world repositories, collaborator churn and social engagement may occur due to organizational or interpersonal dynamics. Such events are treated as **out-of-scope conditions** for the routing model. This assumption is necessary to isolate platform-level detectability from uncontrolled social interference and to preserve the interpretability of empirical indistinguishability measurements.

---

## Detectability of Repository Population Characteristics

**Throughout all DeployStega experiments, the sender and the receiver are the only repository collaborators.**  

Accordingly, DeployStega does **not** model detectability arising from repository-level population characteristics, including (but not limited to):
- collaborator count,
- social graph structure,
- repository popularity, age, or external visibility.

This choice reflects the core objective of DeployStega: to evaluate whether *replacing a single benign user’s interaction log with a covert user’s log* produces a statistically detectable deviation in routing, behavioral, or semantic aspects, **holding the surrounding repository context constant**. Allowing collaborator population to vary would introduce uncontrolled social and organizational factors that are orthogonal to the covert signaling mechanism under study.

---

## Scope Limitation and Justification

DeployStega intentionally abstracts away social, organizational, and interpersonal dynamics in order to:
- enable precise, reproducible measurement of covert detectability,
- align with differential-privacy-style neighboring-dataset formulations,
- avoid conflating linguistic and behavioral indistinguishability with unmodeled human reactions.

Including third-party collaborators would require explicit modeling of human response behavior, notification handling, and off-platform communication—substantially expanding scope and introducing confounding variables orthogonal to the system-level research question.

Modeling such dynamics is deferred to future work and does not diminish the validity of DeployStega’s core contributions.
