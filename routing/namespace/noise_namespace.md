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

## Interaction Class: Events

### Description
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

## Interaction Class: Starring

### Description
Starring represents a per-user bookmarking action that records a GitHub user’s interest in a repository.
Specifically, a star is a persistent preference indicator used for discovery, ranking, and personal organization.

### Identifier Fields
- owner: string
- repo: string
- viewer: string

### Addressability (Sender and Receiver)
#### View a repository’s stargazers (who starred it)
- **GUI URL:** https://github.com/{owner}/{repo}/stargazers

### Notes and Boundaries
- **Stars are stateful, not immutable logs.**  
  The star relationship persists until explicitly removed.
- **List views are observational and can be incomplete due to visibility constraints.**  
  Private repositories and user privacy settings can affect what appears in stargazer/starred listings.
- **Pagination, ordering, and timestamp media types are presentation-layer details.**  
  Query parameters such as `per_page`, `page`, `sort`, `direction`, and optional timestamps, including media types,
  do not define separate interaction surfaces in this model.

---

## Interaction Class: Watching 

### Description
The Watching class captures all users subscribed to (in other words, watching) a repository.
This class does **not** model subscription changes, notification preferences, or any snapshot-mutating actions.

### Identifier Fields
- owner: string  
- repo: string  

### Addressability (Sender and Receiver)
#### List all users subscribed a repository
- **GUI URL:** https://github.com/{owner}/{repo}/watchers

### Notes and Boundaries
- **Activities beyond visiting the URL are not modeled.**  
  Viewing subscribed users' profiles, following their accounts, or attempting to order/filter the list of subscribors are out of scope. 

---

## Interaction Class: Branches

### Description
Branches are **named, mutable references** to a sequence of commits.

### Identifier Fields
- owner: string  
- repo: string  
- branch: string

### Addressability (Sender and Receiver)
#### View list of branches in a repository
- **GUI URL:**  https://github.com/{owner}/{repo}/branches

#### View a specific branch
- **GUI URL:**  
https://github.com/{owner}/{repo}/tree/{branch}

### Notes and Boundaries
- Branch creation, renaming, deletion, merging, syncing, or protection changes are explicitly excluded.
- No branch identifier minting is modeled.
- Further query parameters and UI filters are treated as presentation-layer refinements, not distinct interactions.

---

## Interaction Class: Actions

### Description
Actions model **inspection of available GitHub Actions workflows and templates** within a repository.  

### Identifier Fields
- owner: string  
- repo: string  

### Addressability (Sender and Receiver)
##### View available workflow templates
- **GUI URL:** https://github.com/{owner}/{repo}/actions/new

### Notes and Boundaries
- This interaction is **purely observational** and does not start, schedule, or execute workflows.
- Further queries to filter or modify presence, ordering, or availability of workflow templates are **presentation-level variations** of the same interaction class.

---

## Interaction Class: Repository Governance Settings

### Description
Repository Governance Settings expose administrative configurations governing repository ownership, access control, branch rules, tag protections, and rulesets.  

### Identifier Fields
- owner: string  
- repo: string  

### Addressability (Sender and Receiver)
#### View general repository settings
- **GUI URL:** https://github.com/{owner}/{repo}/settings

#### View repository settings related to collaborators
- **GUI URL:** https://github.com/{owner}/{repo}/settings/access

#### View repository settings related to branches
- **GUI URL:** https://github.com/{owner}/{repo}/settings/branches

#### View repository settings related to tags
- **GUI URL:** https://github.com/{owner}/{repo}/settings/tag_protection

#### View repository settings related to rulesets
- **GUI URL:** https://github.com/{owner}/{repo}/settings/rules

### Notes and Boundaries
- Any mutation of repository settings is excluded to avoid non-linguistic signaling.  
- Visibility of these pages depends on collaborator status.

---

## Interaction Class: Automation & Execution Settings

### Description
Automation & Execution Settings expose configuration state related to CI/CD workflows, runners, and deployment environments.  

### Identifier Fields
- owner: string  
- repo: string  

### Addressability (Sender and Receiver)
#### View general automation and execution settings
- **GUI URL:** https://github.com/{owner}/{repo}/settings/actions

#### View automation and execution settings related to runners
- **GUI URL:** https://github.com/{owner}/{repo}/settings/actions/runners

#### View automation and execution settings related to environments
- **GUI URL:** https://github.com/{owner}/{repo}/settings/environments

### Notes and Boundaries
- This interaction is observational only and does not start workflows, alter runner states, or modify anything else.

---

## Interaction Class: Security & Secrets Settings

### Description
Security & Secrets Settings expose repository security posture, including secret storage, deploy keys, and security analysis configuration.  

### Identifier Fields
- owner: string  
- repo: string  

### Addressability (Sender and Receiver)
#### View general security and secrets settings
- **GUI URL:** https://github.com/{owner}/{repo}/settings/security_analysis

#### View security and secrets settings related to keys
- **GUI URL:** https://github.com/{owner}/{repo}/settings/keys

#### View security and secrets settings related to actions
- **GUI URL:** https://github.com/{owner}/{repo}/settings/secrets/actions

#### View security and secrets settings related to codespaces
- **GUI URL:** https://github.com/{owner}/{repo}/settings/secrets/codespaces

#### View security and secrets settings related to dependabot
- **GUI URL:** https://github.com/{owner}/{repo}/settings/secrets/dependabot

### Notes and Boundaries
- This interaction does not add, remove, rotate, or modify secrets or keys.  
- Security scanners, alerts, and analyses are observed, not triggered.

---

## Interaction Class: Integrations & Extensions Settings

### Description
Integrations & Extensions Settings expose configurations related to third-party services, webhooks, and development environments connected to the repository.

### Identifier Fields
- owner: string  
- repo: string  

### Addressability (Sender and Receiver)
#### View general integrations and extensions
- **GUI URL:** https://github.com/{owner}/{repo}/settings/hooks

#### View integrations and extensions related to installations
- **GUI URL:** https://github.com/{owner}/{repo}/settings/installations

#### View integrations and extensions related to codespaces
- **GUI URL:** https://github.com/{owner}/{repo}/settings/codespaces

### Notes and Boundaries
- Webhooks, installations, and codespaces are not created, removed, or edited.

---

## Interaction Class: AI & Model Policy Settings

### Description
AI & Model Policy Settings expose policy controls governing AI-assisted features, including Copilot behaviors and model access rules.  

### Identifier Fields
- owner: string  
- repo: string  

### Addressability (Sender and Receiver)
#### View general AI and model policies
- **GUI URL:** https://github.com/{owner}/{repo}/settings/copilot/code_review

#### View AI and model policies related to coding agents
- **GUI URL:** https://github.com/{owner}/{repo}/settings/copilot/coding_agent

#### View AI and model policies related to access policies
- **GUI URL:** https://github.com/{owner}/{repo}/settings/models/access-policy

### Notes and Boundaries
- This interaction does not enable, disable, or modify AI behavior.

---

## Interaction Class: Publishing & Notification Settings

### Description
Publishing & Notification Settings expose configurations related to public-facing outputs and notification preferences for the repository.

### Identifier Fields
- owner: string  
- repo: string  

### Addressability (Sender and Receiver)
#### View publishing and notification settings
- **GUI URL:** https://github.com/{owner}/{repo}/settings/pages

### Notes and Boundaries
- This interaction does not publish content or send notifications.  
- GitHub Pages configuration and notification preferences are observed only.

---

## Interaction Class: Repository Security

### Description
Repository Security Overview exposes **derived security and risk posture** for a repository, including vulnerability alerts, dependency update status, and published security policies.

### Identifier Fields
- owner: string  
- repo: string  

### Addressability (Sender and Receiver)
#### View repository security overview
- **GUI URL:** https://github.com/{owner}/{repo}/security

### Notes and Boundaries
- This interaction **does not**:
  - enable or disable security features
  - acknowledge alerts
  - configure Dependabot
  - edit security policies
- Navigation between subpages carries **no meaning**.

---

## Interaction Class: Dependency Network Inspection

### Description
Dependency Network Inspection exposes **derived, system-computed views** of a repository’s dependency topology and update relationships.  
These views reflect how the repository depends on external packages and how dependency-related updates propagate, without enabling configuration or control.

### Identifier Fields
- owner: string  
- repo: string  

### Addressability (Sender and Receiver)
#### View repository dependency network
- **GUI URL:** https://github.com/{owner}/{repo}/network/dependencies  

#### View dependency-related updates
- **GUI URL:** https://github.com/{owner}/{repo}/network/updates

#### View all forks in tree-mode
- **GUI URL:** https://github.com/{owner}/{repo}/network/members

### Notes and Boundaries
- These pages do **not** modify repository configuration, security posture, or automation behavior.
- Pagination, layout, and further query filtering are treated as **presentation-layer behavior**, not distinct interactions.

---

## Interaction Class: Forks

### Description

Forks expose a **derived, system-maintained view** of repositories that were created as forks of the current repository.  

### Identifier Fields
- owner: string  
- repo: string  

### Addressability (Sender and Receiver)

#### View all forks of the repository
- **GUI URL:** https://github.com/{owner}/{repo}/forks

### Notes and Boundaries

- **Fork creation is not modeled.**  
  Creating a fork is a state-mutating, externally visible action and is explicitly excluded.
- **Fork existence is not modeled.**  
  Whether forks appear depends on actions taken by other users and is outside the model’s control.
- **Sorting, filtering, and pagination are presentation-layer behaviors.**  
  UI controls or query parameters do not constitute distinct interaction surfaces.
