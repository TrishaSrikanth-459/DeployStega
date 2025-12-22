# Routing Namespace and Identifier Schemas

## Overview
This document defines the complete routing namespace used by DeployStega.
The routing namespace enumerates all addressable artifact classes exposed
by the application and specifies their identifier schemas.

The namespace is structural only: it specifies what artifacts exist and
how they are identified, not when or how they are accessed.

## Sender and Receiver Interaction Roles

The routing namespace enumerates addressable artifact classes independent
of actor role.

We distinguish between two interaction roles:

- **Sender**: an account capable of creating, modifying, or deleting
  artifacts in order to encode information.
- **Receiver**: an account that accesses existing artifacts through
  standard, read-only interactions in order to observe information.

Sender and receiver interactions need not use identical API endpoints
or HTTP methods. Sender actions may create or modify artifacts using
write-capable interfaces, while receiver actions reference the same
artifact identifiers through read-only, user-facing access mechanisms
(e.g., web URLs).

Routing semantics depend on shared artifact identifiers, not on the
specific API endpoints, permissions, or HTTP verbs used to access them.

## Noise and Benign Activity

The routing namespace includes artifact classes that appear in benign
platform activity regardless of whether they are used for signaling.

The presence of benign accesses to routing artifacts is intentional.
Noise is modeled implicitly through the natural prevalence and access
distribution of artifact classes, rather than through separate
noise-specific artifacts.

No artifact in the namespace is assumed to be signaling by default.

## Access-control considerations
Identifier immutability claims are independent of access permissions.
Repositories and other artifacts may expose different metadata fields depending
on viewer permissions, but identifier fields remain stable across all access
levels.

We assume that both sender and receiver possess legitimate access to any
artifacts referenced for routing, appropriate to their respective roles.
Specifically:
- The sender is authorized to create or modify artifacts used for signaling.
- The receiver is authorized to access (view) those artifacts through
standard read-side interfaces.

Access-control enforcement is treated as external to the routing model and does
not affect routing feasibility or detectability, provided that identifier
addressability is preserved.

## Access Failure Handling
Artifact access or retrieval—by either sender or receiver—may result in non-200
responses (e.g., 301, 403, 404) due to network conditions, repository evolution,
permission changes, or platform behavior.

All such outcomes are treated as access attempts for logging and
observability purposes, since the access was explicitly initiated by the
account. 

## Access Mechanisms
The sender is modeled as interacting with artifacts through legitimate,
write-capable interfaces consistent with normal collaborator behavior.

The receiver is modeled as accessing artifacts exclusively through
standard, user-facing GitHub web URLs (e.g.,
https://github.com/{owner}/{repo}), as would occur during routine browsing
activity.

The model does not assume programmatic access via the GitHub REST or GraphQL
APIs, nor the use of scripted clients, for receiver behavior. Routing semantics
remain artifact-centric rather than endpoint- or permission-centric.

---

## Artifact Class: Repository

### Description
A GitHub repository is the top-level container for source code, issues, 
pull requests, commits, and related collaborative artifacts.

### Identifier Fields
- owner: string; not case sensitive
- repo: string; not case sensitive.

### Identifier Construction Rule
A repository is uniquely identified by the ordered pair (owner, repo), where 
owner is the user or organization name and repo is the repostiory name. 

### Addressability
1. Retrieves the specified repository
   REST API: GET /repos/{owner}/{repo}
   URL: https://github.com/{owner}/{repo}

### Notes
- The sender and receiver are assumed to be collaborators within an existing repository.
  Repository existence is treated as environmental configuration, not a signaling event.
- Repository creation, deletion, ownership changes, visibility changes, and other
  governance- or policy-level operations are excluded because they are rare, high-salience
  actions not suitable for covert routing.
- Fork relationships introduce additional metadata but do not change the (owner, repo) identifier.
- Issue edits (title, body, labels, assignees, lock state, open/closed) do not alter
  the identifier.
- Issue transfer to another repository changes the identifier namespace
  from (owner₁, repo₁, issue_number) to (owner₂, repo₂, issue_number).
- Issue deletion permanently renders the identifier non-addressable
  (404/410). Routing is terminated upon deletion.

---

## Artifact Class: Issue

### Description
A GitHub issue represents a tracked unit of work, discussion, or a bug
report associated with a specific repository.

### Identifier Fields
- owner: string; not case sensitive
- repo: string; not case sensitive
- issue_number: integer

### Identifier Construction Rule
An issue is uniquely identified by the ordered triple 
(owner, repo, issue_number), where:
- owner is the repository owner (user or organization)
- repo is the repository name
- issue_number is the repository-scoped numeric
  identifier assigned at creation.
Issue identifiers are repository-scoped and immutable once assigned.

### Addressability (Sender)
1. Creates a new issue
   REST API: POST /repos/{owner}/{repo}/issues
   Web URL: https://github.com/{owner}/{repo}/issues/new
2. Modifies mutable fields of an existing issue
   REST API: PATCH /repos/{owner}/{repo}/issues/{issue_number}
   Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}/edit

### Addressability (Receiver)
1. Access specific issues
   REST API: GET /repos/{owner}/{repo}/issues/{issue_number}
   Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}

### Notes
- GitHub exposes pull requests through issue endpoints; this affects API
  responses only, not identifier structure.
- Locking conversations, modifying labels, changing assignees, or toggling
  open/closed state do not change the identifier.
- Issue transfer to another repository changes the identifier namespace
  from (owner₁, repo₁, issue_number) to (owner₂, repo₂, issue_number).
- Issue deletion permanently renders the identifier non-addressable.
  Routing is terminated upon deletion.

---

## Artifact Class: PullRequest

### Description
A GitHub pull request represents a proposed set of changes from
a source branch into a target branch within a repository, along
with associated discussion and review activity.

### Identifier Fields
- owner: string; not case sensitive
- repo: string; not case sensitive
- pull_number: integer; not case sensitive

### Identifier Construction Rule
A pull request is uniquely identified by the ordered triple
(owner, repo, pull_number).

The pull_number is assigned at creation time, is unique within
a repository, and remain stable for the lifetime of the pull
request.

### Addressability (Sender)
1. Creates a new pull request
   REST API: POST /repos/{owner}/{repo}/pulls  
   Web URL: https://github.com/{owner}/{repo}/compare
2. Modifies mutable pull request fields
   REST API: PATCH /repos/{owner}/{repo}/pulls/{pull_number}  
   Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}/edit
3. Updates the pull request’s head branch
   REST API: PUT /repos/{owner}/{repo}/pulls/{pull_number}/update-branch  
   Web URL: https://github.com/{owner}/{repo}/pull/{pull_number} 

### Addressability (Receiver)
1. REST API: GET /repos/{owner}/{repo}/pulls/{pull_number}
   Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}

### Notes
- Pull request edits (title, body, draft status), state transitions
  (open, closed, merged), and branch updates do not alter
  (owner, repo, pull_number).
- Repository rename or ownership transfer changes the identifier from
  (owner₁, repo₁, pull_number) to (owner₂, repo₂, pull_number).
- Pull request deletion or loss of access renders the identifier
  non-addressable. Routing is terminated upon deletion.
- Replies form additional comments with their own identifiers; they do not
  alter the parent comment’s identity.

---

## Artifact Class: Commits

### Description
A GitHub commit represents a single immutable snapshot of repository state,
identified by a cryptographic hash and addressable within a repository.

### Identifier Fields
- owner: string; not case sensitive
- repo: string; not case sensitive
- commit_sha: hexadecimal hash; case sensitive

### Identifier Construction Rule
A commit is uniquely identified by the ordered tuple
(owner, repo, commit_sha), where commit_sha is the full commit hash
The commit hash is content-addressed and immutable once created.

### Addressability (Sender)
Commit creation does not correspond to a distinct, user-visible
URL at creation time. Instead, commits are side effect of
sender interactions with file-editing interfaces.
1. Edit existing file
   Web URL: https://github.com/{owner}/{repo}/edit/{branch}/{path}
2. Create new file
   Web URL: https://github.com/{owner}/{repo}/new/{branch}/{path}
Submitting changes from these pages triggers an internal form submission
that creates a new commit and assigns a commit_sha. .

### Addressability (Receiver)
1. Access specified commits
   REST API: GET /repos/{owner}/{repo}/commits/{commit_sha}
   Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}

### Notes
- Commit identifiers (commit_sha) are content-addressed and immutable.
  No GitHub operation can modify an existing commit’s hash.
- Branch movement, rebasing, force-pushes, or pull request association
  changes do not alter the identifier.
- Repository rename or ownership transfer preserves commit identity under
  the new namespace (owner₂, repo₂, commit_sha)
- Commit deletion renders the identifier non-addressable. Routing is terminated
  upon deletion

---

## Artifact Class: Issue comments

### Description
An IssueComment is a user-authored comment attached to a specific issue
within a GitHub repository. Issue comments are routinely accessed during
code review, debugging, and project coordination.

### Identifier Fields
- owner: string; not case sensitive
- repo: string; not case sensitive
- issue_number: integer
- comment_id: integer

### Identifier Construction Rule
An issue comment is uniquely identified by the ordered tuple
(owner, repo, issue_number, comment_id).
- issue_number identifies the parent issue within the repository.
- comment_id identifies the specific comment within that issue.

All identifier fields are immutable once the comment is created.
Issue transfers or repository renames preserve the comment’s 
identity relative to the updated (owner, repo) namespace.

### Addressability (Sender)
1. Create an issue comment
   REST API: POST /repos/{owner}/{repo}/issues/{issue_number}/comments
   Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}
2. Edit an existing issue comment
   REST API: PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}
   Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}#issuecomment-{comment_id}
3. https://github.com/{owner}/{repo}/issues/{issue_number}#issuecomment-{comment_id}
   REST API: DELETE /repos/{owner}/{repo}/issues/comments/{comment_id}
   Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}

### Addressability (Receiver)
1. Access specified issue comment
   REST API: GET /repos/{owner}/{repo}/issues/{issue_number}/comments
   Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}#issuecomment-{comment_id}

### Notes
- Comment edits do not alter the identifier.
- Issue or repository transfer preserves comment identity under the updated
  namespace
- Comment deletion permanently removes addressability. Routing is
  terminated upon deletion.

---

## Artifact Class: Pull Request Review Comments

### Description
A PullRequestReviewComment is a user-authored comment
attached to a specific pull request, typically associated
with a code diff or review discussion. These comments
are routinely accessed during code review workflows.

### Identifier Fields
- owner: string; not case sensitive
- repo: string; not case sensitive
- pull_number: integer
- comment_id: integer

### Identifier Construction Rule
A pull request review comment is uniquely identified by the ordered tuple
(owner, repo, pull_number, comment_id).
- owner and repo identify the repository namespace.
- pull_number identifies the parent pull request within the repository.
- comment_id identifies the specific review comment.
All identifier fields are immutable once the comment is created.
Repository renames or ownership transfers preserve the comment’s
identity relative to the updated (owner, repo) namespace.

### Addressability (Sender)
1. Create a new pull request review comment
   REST API: POST /repos/{owner}/{repo}/pulls/{pull_number}/comments
   Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}
2. Reply to an existing pull request review comment
   REST API: POST /repos/{owner}/{repo}/pulls/{pull_number}/comments/{comment_id}/replies
   Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}#discussion_r{comment_id}
3. Edit an existing pull request review comment
   REST API: PATCH /repos/{owner}/{repo}/pulls/comments/{comment_id}
   Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}#discussion_r{comment_id}
4. Delete a pull request review comment
   REST API: DELETE /repos/{owner}/{repo}/pulls/comments/{comment_id}
   Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}
  
### Addressability (Receiver)
1. Access specified pull request review comments
   REST API: GET /repos/{owner}/{repo}/pulls/comments/{comment_id}
   Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}#discussion_r{comment_id}

### Notes
- Edits, replies, resolution status, or review state changes do not alter
  the identifier.
- Replies create new comments with distinct identifiers and do not modify
  the parent comment’s identifier.
- Repository rename or ownership transfer preserves comment identity under
  the updated namespace.
- Deletion permanently removes addressability, Routing is terminated upon deletion.

---

## Artifact Class: CommitComment

### Description
A commit comment is a user-authored comment attached to a specific commit,
used for code review, clarification, or discussion at the commit level.

### Identifier Fields
- owner: string; not case sensitive
- repo: string; not case sensitive
- comment_id: integer

### Identifier Construction Rule
A commit comment is uniquely identified by the ordered tuple
(owner, repo, comment_id), where:
- owner is the user or organization name owning the repository
- repo is the repository name
- comment_id is a globally unique integer identifier assigned by GitHub
The comment_id uniquely identifies the comment within the repository,
independent of the commit SHA on which it appears.

### Addressability (Sender)
1. Create a new commit comment
   REST API: POST /repos/{owner}/{repo}/commits/{commit_sha}/comments
   Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}
2. Edit an existing commit comment
   REST API: PATCH /repos/{owner}/{repo}/comments/{comment_id}
   Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}#commitcomment-{comment_id}
3. Delete a commit comment
   REST API: DELETE /repos/{owner}/{repo}/comments/{comment_id}
   Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}

### Addressability (Receiver)
1. Access specified commit comments
   REST API: GET /repos/{owner}/{repo}/comments/{comment_id}
   Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}#commitcomment-{comment_id}

### Notes
- Comment edits do not alter the identifier.
- Deletion permanently removes addressability. Routing is terminated upon deletion.
- Repository rename or ownership transfer preserves comment identity under
  the updated namespace.

---

