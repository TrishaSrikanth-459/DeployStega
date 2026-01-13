## Security Scope and Adversary Model (DeployStega)

This section formally delineates **the security properties evaluated by DeployStega**, **those explicitly excluded from consideration**, and **the precise adversarial observation capabilities assumed throughout the experimental pipeline**. These distinctions are essential for interpreting empirical results correctly and for avoiding category errors between *covert-communication security* and *implementation-level program security*.

---

## 1. Purpose-Driven Security Scope

DeployStega is **not intended as a production-grade or hardened software system**.  
Rather, it is a **research instrument** designed to empirically evaluate a **differential-privacy–style notion of indistinguishability for covert communication** within a realistic, platform-mediated environment.

Accordingly, all security claims made by DeployStega are **purpose-limited** and scoped strictly to the experimental objectives defined in this work.

---

## 2. Distinct Notions of Security

DeployStega explicitly separates two orthogonal notions of security, only one of which constitutes the object of study.

### 2.1 Covert Communication Security (Primary Research Objective)

This is the **central security property evaluated by DeployStega**.

The system evaluates whether covert communication remains *statistically indistinguishable* from benign activity when an adversary observes platform-level signals, including:

- GitHub artifact content (issues, pull requests, comments, commits)
- Artifact access patterns and routing topology
- Temporal features such as timing, frequency, and ordering of actions
- Cross-user behavioral correlation between sender and receiver accounts

Security is defined **relative to an explicit adversarial capability class** `F`, and is operationalized via an **empirical indistinguishability parameter ε** derived from adversarial classifier advantage, following differential-privacy–inspired methodology.

Formally, this layer addresses the question:

> *Does replacing a benign GitHub interaction log with a covertly generated log induce a statistically detectable shift in observable platform-level features?*

---

### 2.2 Program and Implementation Security (Explicitly Limited)

Implementation-level security is **not an evaluation target** of DeployStega and is intentionally constrained.

DeployStega assumes, for the duration of each experiment:

- Sender and receiver endpoints are **trusted**
- No endpoint compromise occurs (e.g., malware, keylogging, screen capture)
- No adversarial access exists to local files, scripts, environment variables, or browser state
- No adversarial control over the operating system or execution environment

If endpoint compromise occurs, the experimental threat model is **violated**, and the resulting data are no longer meaningful for evaluating covert communication. This limitation is not a design flaw but a necessary boundary: endpoint-level compromise would trivially defeat any text-based steganographic scheme and render the problem ill-posed.

Consequently, DeployStega provides only minimal implementation hygiene (e.g., avoiding unnecessary secret exposure and background services) and makes **no claims of resistance to endpoint-level attacks**.

**Credential and configuration handling note.**  
DeployStega makes **no attempt to cryptographically protect or harden** the `experiment_manifest.json` file or the sender/receiver identifiers once they are placed in the local project directory for execution. These materials are treated as **trusted, out-of-band experimental inputs**. The only enforcement mechanism is a **simple local lockout policy**: after five consecutive invalid identifier entries, the console enforces an increasing time-based lockout (starting at one minute and escalating in fixed steps). This mechanism is intended solely to prevent accidental misuse during experiments, **not** to provide strong authentication or resistance to a determined local adversary.

---

## 3. Adversarial Observation Model

### 3.1 In-Scope Adversarial Capabilities

The adversary is assumed to possess **platform-level visibility over GitHub activity** associated with the sender and receiver accounts, including:

- All GitHub actions performed by those accounts, **across all repositories**
- Artifact-level interactions (views versus mutations)
- Access timing, frequency, and ordering
- Routing structure and access topology
- Behavioral correlation between sender and receiver activity

This model captures the capabilities of realistic observers such as:

- GitHub internal audit and telemetry systems
- Public or enterprise-scale datasets (e.g., GH Archive, GHTorrent)
- Organizational SOC-style monitoring of developer activity

---

### 3.2 Out-of-Scope Adversarial Capabilities

The adversary is **explicitly not assumed** to have access to:

- Endpoint telemetry (operating system, browser internals, local storage)
- Non-GitHub network traffic
- Activity in other applications (e.g., email, messaging platforms)
- Physical surveillance, coercion, or social engineering

Including such capabilities would trivialize detection and invalidate the scientific premise of covert communication analysis. These powers are therefore **intentionally excluded**.

---

### 3.3 Adversary Role Clarification

The adversary is **not modeled as a repository collaborator** and does not participate in repository interactions.  

The adversary:
- observes semantic, behavioral, and routing features extracted from logs,
- does not generate content, comments, or reactions,
- does not influence repository state during the experiment.

Crucially, DeployStega **does not model an active adversary who tampers with the covert communication channel itself** (e.g., by editing artifacts, injecting misleading content, deleting messages, or otherwise interfering with sender–receiver interactions).  
Such an adversary would trivially defeat any application-layer steganographic scheme by disrupting or corrupting the carrier artifacts, rendering detectability analysis ill-posed.

By restricting the adversary to **passive observation of platform-level logs**, DeployStega isolates the core research question:  
whether covert communication can remain statistically indistinguishable from benign activity **under realistic security monitoring**, rather than under channel sabotage.

---

## 4. Repository Scope vs. Platform Scope

Although **all routing and benign interaction URLs are restricted to a single repository**, the adversary’s observation scope is **not limited to that repository alone**.

### Why Not Repository-Only Visibility?

Restricting the adversary to a single repository would artificially weaken detection by precluding realistic comparative analyses, such as:

- Whether a user’s activity in the covert repository deviates from their activity elsewhere on GitHub
- Whether the covert repository itself appears anomalous relative to ordinary repository behavior

Such comparisons are well within the capabilities of real-world platform monitoring and must therefore be permitted.

### Adopted Boundary

> **The adversary is assumed to observe all GitHub-platform activity performed by the sender and receiver accounts, across all repositories, but no off-platform activity and no endpoint-internal state.**

This represents the **strongest realistic adversary** that preserves the scientific validity of the experiment.

---

## 5. Summary

DeployStega evaluates covert communication security under a GitHub platform–level adversary who can observe all repository interactions, routing patterns, and timing behavior of the sender and receiver accounts across GitHub, but who cannot compromise endpoints or observe off-platform activity. Program-level security is intentionally minimal, including unprotected local configuration files and identifiers with only a basic lockout safeguard, because endpoint compromise would trivially defeat steganography and lies outside the experimental threat model. This separation ensures that measured indistinguishability reflects environmental and behavioral plausibility rather than implementation hardening.
