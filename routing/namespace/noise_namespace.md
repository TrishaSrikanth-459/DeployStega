# Benign Interaction Namespace (Resolver-Selected Noise)

## Purpose

This document specifies the **benign interaction namespace** used by **DeployStega** to model **non-signaling background activity**.

The benign interaction namespace consists of **non-signaling GitHub GUI URLs** that are:

- **functions of a specific repository**, meaning their existence and plausibility depend on a particular `(owner, repo)` context,
- selected **deterministically as a function of epoch**,
- used to provide **behavioral feasibility and realism guarantees**,
- **not included in the repository snapshot**, and
- **never used for steganographic encoding or decoding**.

All benign interactions are scoped to **the same repository used for covert communication** and are accessed using **the same GitHub account** that participates in the covert protocol.

No benign interaction URL is global, platform-wide, cross-repository, or unrelated to the covert repository.

These interactions exist solely to introduce **benign cover behavior** and to ensure that resolver outputs remain statistically plausible under external observation.

---

## Design Principles

The benign interaction namespace obeys the following principles:

1. **Non-signaling by construction**  
   No interaction in this namespace carries covert information.

2. **Epoch-selected**  
   URLs are selected deterministically per epoch by the resolver.

3. **Snapshot-independent**  
   URLs are not enumerated from, nor dependent on, snapshot-defined artifacts.

4. **Repository-scoped semantics**  
   Every URL in this namespace is meaningful **only** in the context of a specific repository and would be implausible outside that context.

5. **Collaborator-bounded access**  
   All interactions assume the user is authenticated as a collaborator of the repository used for covert communication.

6. **Actor-agnostic causality**  
   The modeled user may observe events, activities, or notifications **triggered by any repository actor**, including collaborators, maintainers, bots, or automated systems.  
   The identity of the actor who caused the activity is not modeled and carries no weight.

7. **Behavioral plausibility**  
   All interactions correspond to routine GitHub navigation expected of a repository collaborator.

8. **User-setting blind**  
   Interactions that depend on user-specific settings, other than collaborator status on the chosen repository, are not modeled.

---

## Relationship to the Dead-Drop Namespace

The benign interaction namespace is **resolver-adjacent but routing-orthogonal**.

| Property | Dead-Drop Namespace | Benign Interaction Namespace |
|--------|---------------------|------------------------------|
| Selected per epoch | Yes | Yes |
| Snapshot-enumerated | Yes | No |
| Identifier-bound | Yes | No |
| Encodes payload | Yes | No |
| Used for rendezvous | Yes | No |
| Used for feasibility | Yes | Yes |

---

## Environmental and Operational Assumptions

All benign interactions inherit **exactly the same environmental, operational, and platform-level assumptions** as routing (dead-drop) interactions.

This includes identical assumptions regarding:

- network conditions (latency, throttling, outages),
- authentication state and token validity,
- collaborator-level permission and access controls,
- GitHub availability, rate limiting, and UI behavior, and
- client behavior (browser state, cookies, session continuity).

No additional guarantees of reliability, visibility, availability, or privilege are introduced by the benign interaction namespace beyond those already assumed by the routing namespace.

---

## Interaction Class: Notifications

### Description

GitHub sends **repository-scoped discussion activity** - including issues, pull requests, commits, reviews, and state changes — to collaborators via notification threads.

### Addressability (Sender and Receiver)

#### View all notifications arising from specified repository
   - **GUI URL:** https://github.com/notifications?query=repo%3A{owner}%2F{repo}+

### Notes and Boundaries
- **Notification existence is not modeled.**  
  Whether any notification exists at all is outside the model’s control and depends on external factors such as other users’ actions, repository activity levels, timing, and the user's notification settings
- **Notification interactions are not modeled.**  
  Marking read/unread on notifications, subscribing/unscribing to threads, and similar interactions depend on the existence of notifications and are therefore out of scope.
- **No causal assumptions are made.**  
  The model assumes **no causal relationship** between visiting the notification inbox and the existence, visibility, or state transition of any notification.
- **Queries and filters are not modeled.**  
  Inbox filters, search queries, and URL query parameters (e.g., `?repo=`, `?reason=`, `?is=`) are treated as presentation-layer variations of the same base URL and do not constitute distinct modeled interactions.

---
