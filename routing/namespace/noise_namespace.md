# Benign Interaction Namespace (Resolver-Selected Noise)

## Purpose

This document specifies the **benign interaction namespace** used by **DeployStega** to model **non-signaling background activity**.

The benign interaction namespace captures **static, non-signaling GitHub URLs** that are:

- selected **deterministically as a function of epoch**,
- used to provide **behavioral feasibility and realism guarantees**,
- **not included in the repository snapshot**, and
- **never used for steganographic encoding or decoding**.

These interactions exist solely to introduce **benign cover behavior** and to ensure that resolver outputs remain statistically plausible under observation.

---

## Design Principles

The benign interaction namespace obeys the following principles:

1. **Non-signaling by construction**  
   No interaction in this namespace carries covert information.

2. **Epoch-selected**  
   URLs will be selected deterministically per epoch.

3. **Snapshot-independent**  
   URLs are not enumerated from the snapshot.

4. **Behavioral plausibility**  
   All interactions correspond to realistic, routine GitHub navigation.

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

All interactions in the benign interaction namespace inherit **exactly the same environmental, operational, and platform-level assumptions** as the routing (dead-drop) namespace.

In particular:

- **Network conditions**, including latency, packet loss, throttling, transient outages, or routing instability, are assumed to be identical in distribution and effect to those affecting routing interactions.
- **Authentication state**, including token validity, expiration, and scope restrictions, is assumed to be consistent across both namespaces.
- **Permission constraints**, such as repository access level, organization membership, role-based visibility, and private versus public resource access, are assumed to be unchanged.
- **Platform behavior**, including GitHub availability, rate limiting, UI behavior, and REST API semantics, is assumed to follow the same rules as for routing interactions.
- **Client behavior**, including browser state, session cookies, API client configuration, and polling behavior, is assumed to be identical.

No additional reliability, availability, or privilege guarantees are introduced by the benign interaction namespace beyond those already assumed by the routing namespace.

---

## Interaction Class: Notifications

### Description
GitHub delivers notifications as threads, where each thread represents the current discussion of a single artifact, such as an issue, pull request, or commit. This interaction class covers normal notification-related actions, including listing notifications, viewing individual threads, and subscribing to or unsubscribing from notifications. These endpoints are designed for frequent, polling-based access and reflect standard, non-suspicious GitHub usage patterns.

### Identifier Fields
- thread_id: integer  
- owner: string (repository-scoped endpoints only)  
- repo: string (repository-scoped endpoints only)

### Identifier Construction Rules
- A **notification thread** is uniquely identified by `thread_id`, returned by the notifications listing endpoint.
- Repository-scoped notification access is identified by the ordered pair `(owner, repo)`.

### Authentication Constraints
- These endpoints **only support classic personal access tokens**.
- Fine-grained personal access tokens, GitHub App user tokens, and GitHub App installation tokens are **not supported**.

### Addressability (Sender and Receiver)
### Notifications Inbox (User-Level)

#### List all notification threads for the authenticated user (most recent first)
- **GUI URL:** https://github.com/notifications

#### Mark notifications as read (bulk)
- **GUI URL:** https://github.com/notifications
- **GUI action:** Use **“Mark all as read”** (or select notifications and mark as read) in the inbox UI.
- **Note:** This is not a separate navigable URL; it is an action performed on the inbox page.

### Notification Threads (Thread-Level)

#### Open a specific notification thread (view metadata and jump to subject)
- **GUI URL:** https://github.com/notifications
- **GUI action:** Click the notification row → GitHub routes you to the subject page.

#### Mark a notification thread as read
- **GUI URL:** https://github.com/notifications
- **GUI action:** Open the thread (or use row actions); the notification becomes read.

#### Mark a notification thread as done
- **GUI URL:** https://github.com/notifications
- **GUI action:** Use **“Done”** on that notification in the inbox UI.
- **Note:** This is not a stable “visit this URL” operation; it is a UI action.

### Thread Subscriptions (GUI)

#### View subscription status for particular subject
- **GUI URL (depends on subject type):**
  - **Issue URL:** https://github.com/{owner}/{repo}/issues/{issue_number}
  - **Pull Request URL:** https://github.com/{owner}/{repo}/pull/{pull_number}
- **GUI element:** View **“Subscribe / Unsubscribe”** in the right-side panel.

#### Set subscription state (subscribe / unsubscribe) for particular subject
- **GUI URL (depends on subject type):**
  - **Issue URL:** https://github.com/{owner}/{repo}/issues/{issue_number}
  - **Pull Request URL:** https://github.com/{owner}/{repo}/pull/{pull_number}
- **GUI action:** Toggle **Subscribe / Unsubscribe**.

#### Mute future notifications for the thread (“ignore” behavior)
- **GUI URL (depends on subject type):**
  - **Issue URL:** https://github.com/{owner}/{repo}/issues/{issue_number}
  - **Pull Request URL:** https://github.com/{owner}/{repo}/pull/{pull_number}
- **GUI action:** Set notifications to **ignore / unsubscribe** (where available).

### Repository-Scoped Notifications (GUI)

#### List notification threads within a specific repository
- **GUI URL:** https://github.com/notifications?query=repo:{owner}/{repo}

#### Mark repository notifications as read
- **GUI URL:** https://github.com/notifications?query=repo:{owner}/{repo}
- **GUI action:** Use bulk **Mark as read** on the filtered results.
- **Note:** There is no stable, separate URL; this is an action performed on the page.


## Notification Visibility and User Settings (Environmental Dependency)

Notification-related interactions are subject to **user-specific GitHub notification settings**, including delivery channels, subscription scope, and ignored repositories. As a result, notification visibility is **not guaranteed**.

DeployStega therefore makes **no assumptions** that notifications:

- exist,
- are unread,
- are delivered to the GitHub web inbox,
- or are visible to the user at any given time.

### Protocol Implications

- Notification interactions are **never required** for correctness.
- Notification interactions are **never used** for encoding or decoding.
- Users may, at any point, skip visiting notification URLs selected by the resolver.
- No fallback, retry, or coordination mechanism is triggered by notification invisibility.

Notification interactions therefore function strictly as **optional benign cover behavior**.

### Notes
- Notification access is **read-oriented** and represents routine GitHub usage.
- Marking notifications as read or done does **not alter underlying artifacts**.
- Notification threads may reference issues, pull requests, or commits, but accessing a notification does not imply interaction with those artifacts.
- Notification threads are assumed to exist prior to interaction.
- Notification creation, deletion, or underlying artifact mutation is **out of scope**.

---
