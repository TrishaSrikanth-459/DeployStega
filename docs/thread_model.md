# Security Scope and Adversary Model Clarification (DeployStega)

This section clarifies **what DeployStega is securing**, **what it is explicitly not securing**, and **the precise limits of adversarial observation** assumed by the experiment. These clarifications are essential to interpret experimental results correctly and to avoid conflating *program security* with *covert-communication security*.

---

## 1. Purpose-Driven Security Scope

DeployStega is **not** designed as a production-grade, hardened application.  
It is a **research instrument** whose sole purpose is to evaluate a **differential-privacy–style notion of covert communication indistinguishability** in a realistic, platform-embedded environment.

Accordingly, DeployStega’s security guarantees are **purpose-limited**.

---

## 2. Two Distinct Notions of “Security”

### 2.1 Covert Communication Security (Primary Research Objective)

This is the **explicit object of study**.

DeployStega evaluates whether covert communication is detectable when an adversary observes:

- GitHub artifact content (issues, comments, PRs, commits, etc.)
- Artifact access patterns and routing topology
- Timing, frequency, and ordering of interactions
- Cross-user correlation between sender and receiver activity

Security is defined **relative to an adversarial capability class `F`**, and measured via **empirical ε** derived from classifier advantage, in line with differential-privacy–style indistinguishability.

This layer answers:
> *Does replacing benign GitHub logs with covert logs cause a statistically detectable shift in observable platform features?*

---

### 2.2 Program / Implementation Security (Explicitly Limited)

This is **not** the research target and is intentionally minimal.

DeployStega assumes:
- the sender and receiver machines are **trusted for the duration of the experiment**
- no endpoint compromise (malware, keylogging, screen capture)
- no adversarial access to local files, scripts, or environment variables
- no adversarial control of the browser or OS

If endpoint compromise occurs, **the experiment’s threat model is violated**, and results are no longer meaningful. This is not a weakness of DeployStega; it is a necessary boundary to keep steganography research well-defined.

DeployStega therefore provides only:
- baseline hygiene (no unnecessary secret output, no network listeners)
- no claims of resistance to endpoint-level attacks

---

## 3. Adversary Observation Powers (Precise Limit)

### 3.1 What the Adversary *Can* Observe (In Scope)

The adversary is assumed to have **GitHub platform–level log visibility** for the sender and receiver accounts, including:

- **All GitHub activity by those accounts**, across:
  - the covert repository
  - *other repositories those same accounts interact with*
- Artifact-level actions:
  - views vs. mutations
  - issue/PR/comment/commit access
- Timing, frequency, and ordering of actions
- Routing structure and access topology
- Sender–receiver behavioral correlation within GitHub

This models:
- GitHub internal audit logs
- GH Archive / GHTorrent–style datasets
- Enterprise SOC-style platform monitoring

---

### 3.2 What the Adversary *Cannot* Observe (Out of Scope)

The adversary is **explicitly not assumed** to have access to:

- endpoint telemetry (OS, browser, files, scripts)
- non-GitHub network traffic
- other applications (Slack, email, terminal usage)
- physical surveillance or coercion

Including such powers would trivialize the problem and render covert communication meaningless.

---

## 4. Repository Scope vs. Platform Scope

Although **all routing and benign URLs are restricted to a single repository**, the adversary’s view is **not** restricted to that repository.

### Why not repo-only visibility?

Limiting the adversary to a single repository would artificially weaken detection by preventing comparisons such as:

- “Is this repository unusually active for this user?”
- “Does this user’s behavior in this repo differ from their behavior elsewhere?”

Such comparisons are realistic and must be allowed.

### Why not global (non-GitHub) visibility?

Allowing observation of all user activity everywhere (web, OS, physical world) would invalidate steganographic analysis entirely and is therefore excluded.

### Final Boundary (Adopted)

> **The adversary observes all GitHub-platform activity performed by the sender and receiver accounts, across all repositories, but nothing outside GitHub and nothing inside endpoint devices.**

This is the **strongest realistic adversary** that preserves the scientific validity of the experiment.

---

## 5. Summary (One-Paragraph Statement)

DeployStega evaluates covert communication security under a GitHub platform–level adversary who can observe all repository interactions, routing patterns, and timing behavior of the sender and receiver accounts across GitHub, but who cannot compromise endpoints or observe off-platform activity. Program-level security is intentionally minimal, as endpoint compromise would trivially defeat steganography and lies outside the experiment’s threat model. This separation ensures that measured indistinguishability reflects environmental and behavioral plausibility rather than implementation hardening.
