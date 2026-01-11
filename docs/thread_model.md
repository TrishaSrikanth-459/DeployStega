# Security Scope and Adversary Model (DeployStega)

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

Consequently, DeployStega provides only minimal implementation hygiene (e.g., no unnecessary secret exposure, no background services) and makes **no claims of resistance to endpoint-level attacks**.

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

## 4. Repository Scope vs. Platform Scope

Although **all routing and benign interaction URLs are restricted to a single repository**, the adversary’s observation scope is **not limited to that repository alone**.

### Why Not Repository-Only Visibility?

Restricting the adversary to a single repository would artificially weaken detection by precluding realistic comparative analyses, such as:

- Whether a user’s activity in the covert repository deviates from their activity elsewhere
- Whether the repository itself appears anomalous relative to the user’s global GitHub behavior

Such comparisons are well within the capabilities of real-world platform monitoring and must therefore be permitted.

### Why Not Global (Off-Platform) Visibility?

Conversely, granting the adversary visibility into all user activity outside GitHub (e.g., web browsing, OS behavior, physical actions) would trivialize covert communication and render the experimental question ill-defined. Such omniscient adversaries are therefore excluded.

### Adopted Boundary

> **The adversary is assumed to observe all GitHub-platform activity performed by the sender and receiver accounts, across all repositories, but no off-platform activity and no endpoint-internal state.**

This represents the **strongest realistic adversary** that preserves the scientific validity of the experiment.

---

## 5. Summary

DeployStega evaluates covert communication security under a GitHub platform–level adversary who can observe all repository interactions, routing patterns, and timing behavior of the sender and receiver accounts across GitHub, but who cannot compromise endpoints or observe off-platform activity. Program-level security is intentionally minimal, as endpoint compromise would trivially defeat steganography and lies outside the experimental threat model. This separation ensures that measured indistinguishability reflects environmental and behavioral plausibility rather than implementation hardening.
