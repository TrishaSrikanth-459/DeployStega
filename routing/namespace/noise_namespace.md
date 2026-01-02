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

#### Global Notifications (User-Level)

1. List all notification threads for the authenticated user, sorted by most recently updated.
   - REST API: `GET /notifications`
   - URL: `https://api.github.com/notifications`
2. Marks all notifications as read up to an optional `last_read_at` timestamp.
   - REST API: `PUT /notifications`
   - URL: `https://api.github.com/notifications`

#### Notification Threads (Thread-Level)

3. Retrieves metadata for a specific notification thread, including its repository, subject, reason, and timestamps.
   - REST API: `GET /notifications/threads/{thread_id}`
   - URL: `https://api.github.com/notifications/threads/{thread_id}`
4. Mark a notification thread as read
   - REST API: `PATCH /notifications/threads/{thread_id}`
   - URL: `https://api.github.com/notifications/threads/{thread_id}`
5. Mark a notification thread as done
   - REST API: `DELETE /notifications/threads/{thread_id}`
   - URL: `https://api.github.com/notifications/threads/{thread_id}`

#### Thread Subscriptions

6. Get a thread subscription; returns whether the user is subscribed to or ignoring the thread, along with subscription metadata.
   - REST API: `GET /notifications/threads/{thread_id}/subscription`
   - URL: `https://api.github.com/notifications/threads/{thread_id}/subscription`
7. Set a thread subscription; allows the user to subscribe to or ignore notifications for the thread
   - REST API: `PUT /notifications/threads/{thread_id}/subscription`
   - URL: `https://api.github.com/notifications/threads/{thread_id}/subscription`
8. Delete a thread subscription; mutes future notifications for the thread until the user comments or is @mentioned.
   - REST API: `DELETE /notifications/threads/{thread_id}/subscription`
   - URL: `https://api.github.com/notifications/threads/{thread_id}/subscription`.

#### Repository-Scoped Notifications

9.  Lists all notification threads for the authenticated user within the specified repository
   - REST API: `GET /repos/{owner}/{repo}/notifications`
   - URL: `https://api.github.com/repos/{owner}/{repo}/notifications`

10. Marks all notifications in the specified repository as read.
    - REST API: `PUT /repos/{owner}/{repo}/notifications`
    - URL: `https://api.github.com/repos/{owner}/{repo}/notifications`

### Notification Reasons
Each notification thread includes a `reason` field indicating why the notification was generated.  
Reasons include (but are not limited to):

- `assign`
- `author`
- `comment`
- `mention`
- `review_requested`
- `subscribed`
- `state_change`
- `ci_activity`
- `security_alert`

The reason is **thread-specific** and may change over time.

### Notes
- Notification access is **read-oriented** and represents routine GitHub usage.
- Marking notifications as read or done does **not alter underlying artifacts**.
- Notification threads may reference issues, pull requests, or commits, but accessing a notification does not imply interaction with those artifacts.
- Notification threads are assumed to exist prior to interaction.
- Notification creation, deletion, or underlying artifact mutation is **out of scope**.

---
