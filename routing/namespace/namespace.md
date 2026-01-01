# Routing Namespace and Identifier Schemas

## Overview
This document defines the complete routing namespace used by DeployStega.
The routing namespace enumerates all addressable artifact classes exposed
by the application and specifies their identifier schemas.

The namespace is structural only: it specifies what artifacts exist and
how they are identified, not when or how they are accessed.

---

## Sender and Receiver Interaction Roles (with Initial Permission Assumptions)
The routing namespace enumerates addressable artifact classes independent
of actor role.

We distinguish between two interaction roles:

- **Sender**: an account capable of creating, modifying, or deleting
  artifacts in order to encode information.
- **Receiver**: an account that accesses existing artifacts through
  standard, read-only interactions in order to observe information.

### Initial Permission Assumption (Explicit)
At experiment start, **both sender and receiver are assumed to be legitimate,
non-admin collaborators** on the same repository, with the following minimum
permissions:

- **Sender permissions (write-level collaborator)**  
  The sender has sufficient permissions to:
  - create and edit issues
  - open and edit pull requests
  - create commits via the GitHub web interface
  - create, edit, and delete issue comments, pull request review comments,
    and commit comments  

  The sender is **not** assumed to have repository administrator,
  organization owner, or policy-management privileges.

- **Receiver permissions (read-level collaborator)**  
  The receiver has sufficient permissions to:
  - view the repository
  - view issues, pull requests, commits, and associated comments
    via standard web URLs  

  The receiver is **not** assumed to have write or administrative privileges.
  That they may possess write privileges does not, however, invalidate the experiment. 

Sender and receiver interactions need not use identical API endpoints
or HTTP methods. Routing semantics depend on shared artifact identifiers,
not on the specific API endpoints, permissions, or HTTP verbs used to access them.

API- or web-based actions are treated equivalently so long as they preserve
the artifact’s identifier as defined in this routing namespace.

**All sender actions explicitly enumerated in the Addressability (Sender)
sections are assumed to be identifier-preserving by construction.**
These actions may modify artifact content (e.g., editing comments, issue, or pull requests) 
but do not alter any identifier-defining fields specified in this routing namespace.

---

## Noise and Benign Activity
The routing namespace includes artifact classes that appear in benign
platform activity regardless of whether they are used for signaling.

The presence of benign accesses to routing artifacts is intentional.
Noise is modeled implicitly through the natural prevalence and access
distribution of artifact classes, rather than through separate
noise-specific artifacts.

No artifact in the namespace is assumed to be signaling by default.

---

## Access-Control Considerations
Identifier definitions are independent of permissions such that they specify
**how artifacts are named**, not **who can access or modify them**, and are
assumed to remain stable for the duration of the experiment.

### Experimental Assumption (Permissions and Identifier Stability)
For the scope of the DeployStega experiments, **sender, receiver, and all other
collaborators are assumed to retain their initial permissions for the duration
of the experiment**, and:

- All sender-side mutations and receiver-side observations are assumed
  to be authorized when attempted, and are further assumed to be
  **identifier-preserving**.
- **No actor (including the sender, receiver, or any external collaborator)**
  is assumed to perform actions that would change identifier-defining fields
  as specified in this routing namespace.

In real shared repositories, identifier-changing actions (e.g., repository
renames, issue transfers, history rewriting) may occur due to administrative
decisions or external collaborators. Such events are treated as
**out-of-scope conditions** for the routing model. If an identifier-changing
operation were to occur during an experiment, the run would be considered
**invalidated or aborted**, rather than modeled as a routing failure.

Permission changes and identifier-changing operations are therefore
**out of scope** for the routing model and are not treated as part of the
evaluated threat or failure surface.

---

## Access Failure Handling
Access attempts (sender write-side or receiver read-side) may, in real-world
deployments, fail due to network conditions, platform outages, or policy changes.

### Experimental Assumption (Network and Platform Stability)

For the purposes of the DeployStega experiments, **network connectivity and
GitHub platform availability are assumed to be stable**:
- No adversarial or systematic network failures are injected.
- No GitHub-wide outages or availability disruptions are modeled.
- All attempted accesses are assumed to reach the platform successfully.

This assumption is necessary to focus evaluation on **routing feasibility
and detectability**, rather than on external reliability engineering concerns
that are unrelated to covert signaling structure.

### Consequence
Under this assumption:
- All sender-side actions are assumed to execute successfully.
- All receiver-side accesses are assumed to resolve successfully.

This does **not** imply that DeployStega guarantees delivery in practice,
only that delivery failures arising from permissions or network instability
are explicitly excluded from the experimental scope.

### Justification for No Retransmission or Feedback
Even under idealized access conditions, DeployStega does not assume
retransmission or feedback.

Reliable delivery would require the sender to infer receiver observation
or to receive explicit acknowledgment, introducing detectable coordination,
behavioral coupling, or an out-of-band signaling channel. Such mechanisms
are incompatible with the benign-behavior constraints and feasible-access
logs that govern our routing model.

Accordingly, DeployStega models routing as a **best-effort covert channel**
even under ideal conditions. Reliability, if required, must arise from
encoding redundancy or higher-level protocols outside the routing namespace
itself.

---

## Access Mechanisms
The sender and receiver are modeled as accessing artifacts exclusively
through standard, user-facing GitHub web URLs
(e.g., `https://github.com/{owner}/{repo}`), as would occur during routine
browsing activity.

The model does not assume programmatic access via the GitHub REST or
GraphQL APIs, nor the use of scripted clients.

---

## Artifact Class: Repository

### Description
A GitHub repository is the top-level container for source code, issues, 
pull requests, commits, and related collaborative artifacts.

### Identifier Fields
- owner: string
- repo: string

### Identifier Construction Rule
A repository is uniquely identified by the ordered pair
(owner, repo), where:
- owner: The GitHub username or organization name that owns the repository.
- repo: The repository name within the owner’s namespace.

### Addressability (Sender and Receiver)
1. Retrieves the specified repository
  - REST API: GET /repos/{owner}/{repo}
  - URL: https://github.com/{owner}/{repo}

### Notes
- The sender and receiver are assumed to be collaborators within an existing repository.
  Repository existence is treated as environmental configuration, not a signaling event.
- Fork relationships introduce additional metadata but do not change the (owner, repo) identifier.
- Identifier-changing operations such as repository renames, transfers, or visibility changes
  are **defined by the platform** but are **assumed not to occur within the experimental scope**.

---

## Artifact Class: Issue

### Description
A GitHub issue represents a tracked unit of work, discussion, or a bug
report associated with a specific repository.

### Identifier Fields
- owner: string
- repo: string
- issue_number: integer

### Identifier Construction Rule
An issue is uniquely identified by the ordered triple 
(owner, repo, issue_number), where:
- owner: The GitHub user or organization that owns the repository.
- repo: The repository name in which the issue exists.
- issue_number: The repository-scoped numeric identifier assigned to the issue at creation time.

### Addressability (Sender)
1. Modifies mutable fields of an existing issue
  - REST API: PATCH /repos/{owner}/{repo}/issues/{issue_number}
  - Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}
      - Upon visiting this url, the sender must click the "edit" button on the top right.

### Addressability (Receiver)
1. Access specific issues
  - REST API: GET /repos/{owner}/{repo}/issues/{issue_number}
  - Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}

### Notes
- Editing issue fields (title, body, labels, assignees, lock state, open/closed)
  does not change the identifier.
- Identifier-changing operations such as issue transfer or deletion are platform-defined
  but are **assumed not to occur** within the experimental scope.

---

## Artifact Class: PullRequest

### Description
A GitHub pull request represents a proposed set of changes from
a source branch into a target branch within a repository, along
with associated discussion and review activity.

### Identifier Fields
- owner: string
- repo: string
- pull_number: integer

### Identifier Construction Rule
A pull request is uniquely identified by the ordered tuple
(owner, repo, pull_number), where:
- owner: The GitHub user or organization that owns the repository.
- repo: The repository name containing the pull request.
- pull_number: The repository-scoped numeric identifier assigned when the pull request is created.

### Addressability (Sender) 
1. Modifies mutable pull request fields
   - REST API: PATCH /repos/{owner}/{repo}/pulls/{pull_number}
   - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}
       - Upon visiting the URL, the sender must click "Edit" to the right of the pull request's title to edit the title; the sender must or click "..." and then "Edit" near the top right of the pull request's body to edit the body.
2. Merge the pull request into the target branch
   - REST API: PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge
   - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}
       - Upon visiting the URL, the sender must click "Merge pull request and subsequently type a commit message and extended description before finally clicking "Confirm merge."

### Addressability (Receiver) 
1. View an existing pull request. 
   - REST API: GET /repos/{owner}/{repo}/pulls/{pull_number}
   - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}

### Notes
- Pull request edits, state transitions (draft/open/closed/merged),
  and branch updates do not alter the identifier.
- Identifier-changing operations such as repository rename, transfer,
  or pull request deletion are platform-defined but **assumed not to occur**
  during experiments.

---

## Artifact Class: Commit

### Description
A GitHub commit represents a single immutable snapshot of repository state,
identified by a cryptographic hash and addressable within a repository.

### Identifier Fields
- owner: string
- repo: string
- commit_sha: hexadecimal hash

### Identifier Construction Rule
A commit is uniquely identified by the ordered tuple
(owner, repo, branch, path, commit_sha), where:
- owner: The GitHub user or organization that owns the repository.
- repo: The repository name in which the commit exists.
- commit_sha: The cryptographic hash that uniquely identifies the commit.

### Addressability (Receiver) 
1. Access specified commits
   - REST API: GET /repos/{owner}/{repo}/commits/{commit_sha}
   - Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}

### Notes
- Branch movement, rebasing, or pull request association do not alter the commit identifier.
- Identifier-changing operations such as repository deletion or history rewriting
  are **assumed not to occur** within the experimental scope.

---

## Artifact Class: IssueComment

### Description
An IssueComment is a user-authored comment attached to a specific issue
within a GitHub repository.

### Identifier Fields
- owner: string
- repo: string
- issue_number: integer

### Identifier Construction Rule
An issue comment is uniquely identified by the ordered tuple
(owner, repo, issue_number).

### Addressability (Sender) 
1. Create an issue comment
   - REST API: POST /repos/{owner}/{repo}/issues/{issue_number}/comments
   - Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}
       - Sender must enter the comment's content in the text box under "Add a comment" and subsequently click "comment" to save their changes.
2. Edit an existing issue comment
   - REST API: PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}
   - Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}
       - Sender must click "..." near the top-right of the comment's textbox, click "Edit," enter the comment's content, and finally, click "Update comment."
3. Delete an existing issue comment
   - REST API: DELETE /repos/{owner}/{repo}/issues/comments/{comment_id}
   - Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}
       - Sender must click "..." near the top-right of the comment's textbox, click "Delete," and again, click "Delete."
         
### Addressability (Receiver) 
1. Access specified issue comment
   - REST API: GET /repos/{owner}/{repo}/issues/{issue_number}/comments
   - Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}
       - Reciever must scroll down to the desired comment under the specified issue.

### Notes
- Comment creation, editing, or deletion does not change the identifier.
- Identifier-changing operations such as issue transfer or deletion are
  platform-defined but **assumed not to occur** during the experiment.

---

## Artifact Class: PullRequestComment

### Description
User-authored comments associated with a pull request, either in the
Conversation tab or the Files changed tab.

### Identifier Fields
- owner: string
- repo: string
- pull_number: integer

### Identifier Construction Rule
A pull request comment is uniquely identified by the ordered tuple
(owner, repo, pull_number).

### Addressability (Sender) 
1. Create a new pull request review comment
   - REST API: POST /repos/{owner}/{repo}/pulls/{pull_number}/comments
   - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}/files
       - Sender must hover over "+" to the left of the specific change they wish to comment on, enter the comment's contents in the newly appeared text box, and finally, click "Add review comment."
2. Reply to an existing pull request review comment
   - REST API: POST /repos/{owner}/{repo}/pulls/{pull_number}/comments/{comment_id}/replies
   - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}/files
       - Sender must enter the reply's comments in the textbox underneath the comment they wish to reply to, and finally, click "Add review comment."
3. Edit an existing pull request review comment
   - REST API: PATCH /repos/{owner}/{repo}/pulls/comments/{comment_id}
   - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}/files
       - Sender must click "..." near the top right of the text box of the comment, click "Edit," enter the desired edits in the newly appeared text box, and finally, click "Update comment."
4. Delete a pull request review comment
   - REST API: DELETE /repos/{owner}/{repo}/pulls/comments/{comment_id}
   - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}
       - Sender must click "..." near the top right of the text box of the comment, click "Delete," and finally, click "Ok."
         
### Addressability (Receiver) 
1. Access specified pull request review comments
   - REST API: GET /repos/{owner}/{repo}/pulls/comments/{comment_id}
   - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}/files
       - Reciever must scroll down to the desired comment to the left of this page.

### Notes
- Comment creation, editing, or deletion does not alter the identifier.
- Identifier-changing operations such as pull request deletion or repository
  transfer are **assumed not to occur** within scope.

---

## Artifact Class: CommitComment

### Description
A commit comment is a user-authored comment attached to a specific commit.

### Identifier Fields
- owner: string
- repo: string
- commit_sha: hexadecimal hash

### Identifier Construction Rule
A commit comment is uniquely identified by the ordered tuple
(owner, repo, commit_sha).

### Addressability (Sender) 
1. Edit an existing commit comment
   - REST API: PATCH /repos/{owner}/{repo}/comments/{comment_id}
   - Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}
       - Sender must click "..." near the top right of the comment's text box, click "Edit," enter the desired edits, and finally, click "Update comment." They may do so for either a general comment or a line-specific comment.
         
### Addressability (Receiver) 
1. Access specified commit comments
   - REST API: GET /repos/{owner}/{repo}/comments/{comment_id}
   - Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}
       - Receiver must scroll down to the desired comment on the page.

### Notes
- Comment editing does not alter the identifier.
- Identifier-changing operations such as repository transfer are
  **assumed not to occur** within the experimental scope.

---
