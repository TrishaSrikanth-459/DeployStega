# Benign Interaction Namespace (Resolver-Selected Noise)

## Purpose

This document specifies the **benign interaction namespace** used by **DeployStega** to model **non-signaling background activity**.

The benign interaction namespace consists of **non-signaling GitHub GUI URLs** that are scoped to **the same repository used for covert communication** and are accessed using **the same GitHub account** that participates in the covert protocol.

No benign interaction URL is global, platform-wide, cross-repository, or unrelated to the covert repository.

These interactions exist solely to introduce **benign cover behavior** and to ensure that resolver outputs remain statistically plausible under external observation.

---

## Design Principles

The benign interaction namespace obeys the following principles:

1. **Non-signaling by construction**  
   No interaction in this namespace carries covert information.

2. **Epoch-selected**  
   URLs are selected deterministically per epoch by the resolver.

3. **Repository-scoped semantics**  
   Every URL in this namespace is meaningful **only** in the context of a specific repository and would be implausible outside that context.

4. **Collaborator-bounded access**  
   All interactions assume the user is authenticated as a collaborator of the repository used for covert communication.

5. **Actor-agnostic causality**  
   The modeled user may observe events, activities, or notifications **triggered by any repository actor**, including collaborators, maintainers, bots, or automated systems.  
   The identity of the actor who caused the activity is not modeled and carries no weight.

6. **Behavioral plausibility**  
   All interactions correspond to routine GitHub navigation expected of a repository collaborator.

7. **User-setting blind**  
   Interactions that depend on user-specific settings, other than collaborator status on the chosen repository, are not modeled.

---

## Relationship to the Dead-Drop Namespace

The benign interaction namespace is **resolver-adjacent but routing-orthogonal**.

| Property | Dead-Drop Namespace | Benign Interaction Namespace |
|--------|---------------------|------------------------------|
| Selected per epoch | Yes | Yes |
| Snapshot-enumerated | Yes | No |
| Identifier-bound | Yes | Yes |
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

### Identifier Fields
- owner: string
- repo: string

### Addressability (Sender and Receiver)
#### View all notifications arising from specified repository
   - **GUI URL:** https://github.com/notifications?query=repo%3A{owner}%2F{repo}+

### Notes and Boundaries
- **Notification existence is not modeled.**
  Whether notification(s) exists in the user's inbox depends on other users' actions, the user's notification settings, and when, if at all, the user had marked such notification(s) as read prior to the start of the experiment. All three factors are outside the model's control. 
- **Notification interactions are not modeled.**  
  Marking notification(s) as read depends on the existence of such notification(s). Likewise, subscribing/unscribing to particular threads, such as an issue thread, depends on initial subscribor status - a factor outside the model's control. One cannot subscribe to a thread they are already subscribed to; clicking that button will simply unsubscribe them. 
- **Notification queries and filters are not modeled.**  
  Inbox filters, search queries, and URL query parameters (e.g., `?repo=`, `?reason=`, `?is=`) are treated as presentation-layer variations of the same base URL and do not constitute distinct modeled interactions.

---

# Interaction Class: Events

## Description
Events are immutable activity records emitted by GitHub whenever an actor (humans, bots, automation) performs an action.
Event streams are not real-time views of repository activity; actions may appear in event feeds with a delay ranging from tens of seconds to several hours.
Event feeds include up to **300 events**, limited to **the past 30 days**

### Identifier Fields
- owner: string
- repo: string

### Addressability (Sender and Receiver)
#### View all events specific to the repository
   - **GUI URL:** https://github.com/{owner}/{repo}/activity

### Notes and Boundaries
- **Event existence is not modeled.**  
  Whether event(s) appear at a given time depends on external actor behavior (other collaborators, bots, automation) and platform-side timing.
- **Filtering and scoping controls are not modeled as distinct interactions.**  
  UI-level filters (e.g., by branch, actor, activity type, or time range) and URL query parameters are treated as presentation-layer refinements of the same base URL, not separate interaction endpoints.
- **Detectability impact from filtering is implicit, not explicit.**
  While UI filters can influence detectability, the model does not treat filtering as an independently observable or addressable action. All filtering effects are subsumed into
  the risk profile of visiting the repository activity page.
  
---

# Interaction Class: Starring

## Description
Starring represents a per-user bookmarking action that records a GitHub user’s interest in a repository.
Specifically, a star is a persistent preference indicator used for discovery, ranking, and personal organization.

### Identifier Fields
- owner: string
- repo: string
- viewer: string

### Addressability (Sender and Receiver)
#### View a repository’s stargazers (who starred it)
- **GUI URL:** https://github.com/{owner}/{repo}/stargazers

#### View repositories starred by a user
- **GUI URL:** https://github.com/{username}?tab=stars
- **Notes:** Publicly visible list is constrained by the user’s profile visibility and repository visibility.

### Notes and Boundaries
- **Stars are stateful, not immutable logs.**  
  The star relationship persists until explicitly removed.
- **List views are observational and can be incomplete due to visibility constraints.**  
  Private repositories and user privacy settings can affect what appears in stargazer/starred listings.
- **Pagination, ordering, and timestamp media types are presentation-layer details.**  
  Query parameters such as `per_page`, `page`, `sort`, `direction`, and optional timestamp-including media types
  do not define separate interaction surfaces in this model.

---
