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

All such outcomes are treated as benign access attempts for logging and
observability purposes, since the access was explicitly initiated by the
account. Routing semantics depend solely on artifact addressability and access
attempts, not on retrieval success, response codes, or response contents.

## Receiver Access Mechanism
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
owner is the user or organization name and repo is the repostiory name. Both
fields are case-insensitive and immutable once the repostiory exists, except
under explicit rename or transfer options.

### Addressability
- REST API: GET /repos/{owner}/{repo}
- URL: https://github.com/{owner}/{repo}

### Notes
- Fork relationships introduce parent and source metadata but do not alter
  the repository’s primary identifier.

---

## Artifact Class: Issue

### Description
A GitHub issue represents a tracked unit of work, discussion, or a bug
report associated with a specific repository. Issues are addressable
objects exposed via stable numeric identifiers within a repository.

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

### Addressability
- REST API: GET /repos/{owner}/{repo}/issues/{issue_number}
- Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}

### Notes
- GitHub’s REST API treats pull requests as a subtype of issues; thus, issue
  endpoints may return both issues and pull requests. This distinction does not
  affect identifier structure.
- Issue transfer between repositories results in a 301 response; deletion may
  result in 404 or 410 responses depending on viewer permissions.
- Routing logic depends solely on identifier addressability, not returned content
  representation.

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
a repository, and remains stable for the lifetime of the pull
request.

### Addressability
- REST API: GET /repos/{owner}/{repo}/pulls/{pull_number}
- Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}

### Notes
- Draft status, mergeability state, merge commits, and review outcomes are
  mutable metadata and are not part of the identifier.
- Pull requests are distinct from issues, even though GitHub’s API may expose
  pull requests through issue-related endpoints.
- Repository transfers or renames preserve pull request identity relative to the
  updated (owner, repo) namespace.

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

### Addressability
- REST API: GET /repos/{owner}/{repo}/commits/{commit_sha}
- URL: https://github.com/{owner}/{repo}/commit/{commit_sha}

### Notes
- Branch membership, pull request association, and comparison relationships
  are derived metadata and are not part of the identifier.
- Repository renames or transfers do not alter commit identity relative to the
  updated (owner, repo) namespace.

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

### Addressability
- REST API: GET /repos/{owner}/{repo}/issues/{issue_number}/comments
- Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}#issuecomment-{comment_id}

### Notes
- Issue comments are distinct from pull request review comments.

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

### Addressability
- REST API: GET /repos/{owner}/{repo}/pulls/comments/{comment_id}
- Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}#discussion_r{comment_id}

### Notes
- Pull request review comments are distinct from issue comments.
- Review comments may be associated with specific commits or diff positions,
  but these associations are mutable metadata and are not part of the identifier.

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

### Addressability
- REST API: GET /repos/{owner}/{repo}/comments/{comment_id}
- Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}#commitcomment-{comment_id}

### Notes
- Media-type variants (raw, text, HTML, full) affect only the representation
  of comment content and do not alter the comment’s identifier.
- Access to commit comments may require repository metadata read permissions
  for private repositories
- A 404 Not Found response may indicate lack of access, deletion, or nonexistence.

---

