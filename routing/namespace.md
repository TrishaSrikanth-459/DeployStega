# Routing Namespace Definition

## Overview

This document defines the routing namespace exposed by the GitHub application
under the DeployStega threat model.

The routing namespace enumerates the finite set of artifact classes that are
addressable by both sender and receiver and may be referenced by routing and
dead-drop mechanisms.


## Formal Definition

Let the routing namespace be defined as the finite set:

N = {
  Repository,
  Issue,
  PullRequest,
  Commit,
  IssueComment,
  PullRequestReviewComment,
  CommitComment
}

Each element of N corresponds to a distinct GitHub artifact class that:

- Is addressable via stable identifiers
- Appears in benign GitHub interaction logs
- Is exposed through public GitHub interfaces
- Can be accessed by collaborators of a repository

## Scope and Exclusions

The routing namespace intentionally excludes:

- Timing, ordering, or transition structure between artifacts
- Artifact metadata beyond identifier fields
- Artifact classes requiring organization- or team-level context
- Artifacts not directly tied to repository collaboration workflows

Detailed identifier formats, construction rules, and stability considerations
for each artifact class are specified in `identifier_schemas.md`.

## Consumption

This namespace definition is consumed by:

- Routing and dead-drop resolution logic
- Feasibility checks restricting allowable artifact references
- The Methods and Threat Model sections of the DeployStega paper

No behavioral or semantic assumptions are encoded at this layer.
