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

Sender and receiver interactions need not use identical API endpoints
or HTTP methods. Routing semantics depend on shared artifact identifiers,
not on the specific API endpoints, permissions, or HTTP verbs used to access them.

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
**how artifacts are named**, not **who can access them**.

### Experimental Assumption (Permissions)
For the scope of the DeployStega experiments, **sender and receiver are assumed
to retain their initial permissions for the duration of the experiment**.
Specifically:
- No permission revocation, role change, repository visibility change,
  or organization policy change is assumed to occur.
- All sender-side mutations and receiver-side observations are assumed
  to be authorized when attempted.

This assumption is adopted to isolate routing semantics from administrative
and organizational dynamics, which are orthogonal to the research question
and infeasible to control systematically at experimental scale.

Permission changes are therefore **out of scope** for the routing model and
are not treated as part of the evaluated threat or failure surface.

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

This assumption is necessary to focus evaluation on **routing feasibility,
and detectability**, rather than on external reliability
engineering concerns that are unrelated to covert signaling structure.

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
A repository is uniquely identified by the ordered pair (owner, repo), where 
owner is the user or organization name and repo is the repostiory name. 

### Addressability (Sender and Receiver)
1. Retrieves the specified repository
  - REST API: GET /repos/{owner}/{repo}
  - URL: https://github.com/{owner}/{repo}

### Notes
- The sender and receiver are assumed to be collaborators within an existing repository.
  Repository existence is treated as environmental configuration, not a signaling event.
- Fork relationships introduce additional metadata but do not change the (owner, repo) identifier.
- Issue edits, transfers, deletions, repository renames, transfers, or visibility changes
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
- owner is the repository owner (user or organization)
- repo is the repository name
- issue_number is the repository-scoped numeric
  identifier assigned at creation.

### Addressability (Sender)
1. Creates a new issue
  - REST API: POST /repos/{owner}/{repo}/issues
  - Web URL: https://github.com/{owner}/{repo}/issues/new
2. Modifies mutable fields of an existing issue
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
- Issue transfer or deletion is a platform-defined operation but is **assumed not to occur**
  within the experimental scope.

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
- branch_1: string
- branch_2: string

### Identifier Construction Rule
A pull request is uniquely identified by the ordered triple
(owner, repo, pull_number, branch_1, branch_2).

The pull_number is assigned at creation time and unique within
a repository. The branch_1 and branch_2 fields specifiy the names
of the branch to merge into and the branch that contains
one's new changes, respectively. 

### Addressability (Sender)
1. Creates a new pull request
  - REST API: POST /repos/{owner}/{repo}/pulls  
  - Web URL: https://github.com/{owner}/{repo}/compare/{branch_1}...{branch_2}
      - In the URL, the sender must replace all spaces with "-" symbols
        when referring to branch names
      - Upon visiting the URL, the sender must click "Create a pull request"
        and subsequently add a title and description before again clicking
        "Create a pull request."
2. Modifies mutable pull request fields
  - REST API: PATCH /repos/{owner}/{repo}/pulls/{pull_number}  
  - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}
      - Upon visiting the URL, the sender must click "Edit" to the right
        of the pull request's title to edit the title; the sender must
        or click "..." and then "Edit" near the top right of the pull
        request's body to edit the body.
3. Merge the pull request into the target branch
  - REST API: PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge
  - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}
      -  Upon visiting the URL, the sender must click "Merge pull
         request and subsequently type a commit message and
         extended description before finally clicking "Confirm merge."

### Addressability (Receiver)
1. REST API: GET /repos/{owner}/{repo}/pulls/{pull_number}
  - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}

### Notes
- Pull request edits, state transitions (draft/open/closed/merged),
  and branch updates do not alter the identifier.
- Repository rename, transfer, or pull request deletion are platform-defined
  but **assumed not to occur during experiments**.

---

## Artifact Class: Commits

### Description
A GitHub commit represents a single immutable snapshot of repository state,
identified by a cryptographic hash and addressable within a repository.

### Identifier Fields
- owner: string
- repo: string
- branch: string
- commit_sha: hexadecimal hash

### Identifier Construction Rule
A commit is uniquely identified by the ordered tuple
(owner, repo, branch, commit_sha)

### Addressability (Sender)
Commit creation does not correspond to a distinct, user-visible
URL at creation time. Instead, commits are side effect of
sender interactions with file-editing interfaces.
1. Edit existing file
  - Web URL: https://github.com/{owner}/{repo}/edit/{branch}/{path}
      - Sender must click "Commit changes..." to save their edits.
2. Create new file
  - Web URL: https://github.com/{owner}/{repo}/new/{branch}/{path}
      - {path} should not include the new file name; the sender must
        enter the file's contents and subsequently click "Commit changes..."
        to save their edits.
Submitting changes from these pages triggers an internal form submission
that creates a new commit and assigns a commit_sha.

### Addressability (Receiver)
1. Access specified commits
  - REST API: GET /repos/{owner}/{repo}/commits/{commit_sha}
  - Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}

### Notes
- Branch movement, rebasing, or pull request association do not alter the commit identifier.
- Repository deletion or garbage collection may affect addressability in practice,
  but such events are **assumed not to occur within the experimental scope**.

---

## Artifact Class: Issue comments

### Description
An IssueComment is a user-authored comment attached to a specific issue
within a GitHub repository. Issue comments are routinely accessed during
code review, debugging, and project coordination.

### Identifier Fields
- owner: string
- repo: string
- issue_number: integer
- comment_id: integer

### Identifier Construction Rule
An issue comment is uniquely identified by the ordered tuple
(owner, repo, issue_number).
- issue_number identifies the parent issue within the repository.

### Addressability (Sender)
1. Create an issue comment
  - REST API: POST /repos/{owner}/{repo}/issues/{issue_number}/comments
  - Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}
      - Sender must enter the comment's content in the text box under
        "Add a comment" and subsequently click "comment" to save
        their changes.
2. Edit an existing issue comment
  - REST API: PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}
  - Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}
      - Sender must click "..." near the top-right of the comment's textbox,
        click "Edit," enter the comment's content, and finally, click
        "Update comment."
3. Delete an existing issue comment
  - REST API: DELETE /repos/{owner}/{repo}/issues/comments/{comment_id}
  - Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}
      - Sender must click "..." near the top-right of the comment's textbox,
        click "Delete," and again, click "Delete."
### Addressability (Receiver)
1. Access specified issue comment
  - REST API: GET /repos/{owner}/{repo}/issues/{issue_number}/comments
  - Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}
      - Reciever must scroll down to the desired comment under the specified issue. 

### Notes
- Comment edits do not alter the identifier.
- Comment deletion or issue transfer is platform-defined but **assumed not to occur**
  during the experiment.

---

## Artifact Class: Pull Request Review/Conversation Comments

### Description
A PullRequestReviewComment is a user-authored comment
posted in the "Files changed" tab of a GitHub pull request,
typically associated with a code diff or review discussion.
These comments are routinely accessed during code review workflows.

A PullRequestConversationComment is a top-level, user-authored
comment posted in the "Conversation" tab of a GitHub pull request,
not associated with a specific code line or diff. These comments are
unthreaded.

### Identifier Fields
- owner: string
- repo: string
- pull_number: integer

### Identifier Construction Rule
A pull request comment is uniquely identified by the ordered tuple
(owner, repo, pull_number).
- owner and repo identify the repository namespace.
- pull_number identifies the parent pull request within the repository.

### Addressability (Sender)
1. Create a new pull request conversation comment
  - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}
      - Sender must scroll down to the text box under "Add a comment,"
        enter the comment's contents, and finally, click "comment.
2. Edit an existing pull request conversation commetn
  - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}
      - Sender must click "..." near the top right of the text box
        of the comment, click "Edit," enter the desired edits in the
        newly appeared text box, and finally, click "Update comment."
3. Create a new pull request review comment
  - REST API: POST /repos/{owner}/{repo}/pulls/{pull_number}/comments
  - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}/files
      - Sender must hover over "+" to the left of the specific change
        they wish to comment on, enter the comment's contents in the
        newly appeared text box, and finally, click "Add review comment."
4. Reply to an existing pull request review comment
  - REST API: POST /repos/{owner}/{repo}/pulls/{pull_number}/comments/{comment_id}/replies
  - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}/files
      - Sender must enter the reply's comments in the textbox underneath the comment
        they wish to reply to, and finally, click "Add review comment."
5. Edit an existing pull request review comment
  - REST API: PATCH /repos/{owner}/{repo}/pulls/comments/{comment_id}
  - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}/files
      - Sender must click "..." near the top right of the text box
        of the comment, click "Edit," enter the desired edits in the
        newly appeared text box, and finally, click "Update comment."
6. Delete a pull request review comment
  - REST API: DELETE /repos/{owner}/{repo}/pulls/comments/{comment_id}
  - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}
      - Sender must click "..." near the top right of the text box
        of the comment, click "Delete," and finally, click "Ok."
  
### Addressability (Receiver)
1. Access specified pull request conversation comments
   - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}
       - Reciever must scroll down to the desired comment on this page. 
3. Access specified pull request review comments
  - REST API: GET /repos/{owner}/{repo}/pulls/comments/{comment_id}
  - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}/files
      - Reciever must scroll down to the desired comment to the left
        of this page.

### Notes
- Edits, replies, or review state changes do not alter existing identifiers.
- Deletion or repository transfer is assumed not to occur within scope.

---

## Artifact Class: CommitComment

### Description
A commit comment is a user-authored comment attached to a specific commit,
used for code review, clarification, or discussion at the commit level.

### Identifier Fields
- owner: string
- repo: string
- comment_id: integer

### Identifier Construction Rule
A commit comment is uniquely identified by the ordered tuple
(owner, repo, commit_sha), where:
- owner is the user or organization name owning the repository
- repo is the repository name
- comment_id is a globally unique integer identifier assigned by GitHub

### Addressability (Sender)
1. Create a new commit comment
  - REST API: POST /repos/{owner}/{repo}/commits/{commit_sha}/comments
  - Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}
      -  Sender must either 1) enter the comment's content in the textbox underneath
         "Comments," and finally, click "Comment" or 2) hover over "+" to the left
         of a specific commit line, enter the comment's contents in the newly
         appeared text box, and finally, click "Comment."
2. Edit an existing commit comment
  - REST API: PATCH /repos/{owner}/{repo}/comments/{comment_id}
  - Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}
      - Sender must click "..." near the top right of the comment's
        text box, click "Edit," enter the desired edits, and finally,
        click "Update comment." They may do so for either a general comment
        or a line-specific comment. 
3. Delete a commit comment
  - REST API: DELETE /repos/{owner}/{repo}/comments/{comment_id}
  - Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}
      -  Sender must click "..." near the top right of the comment's
        text box and click "Delete." They will need to click "Delete"
        an additional time if they are deleting a line-specific
        comment. 

### Addressability (Receiver)
1. Access specified commit comments
  - REST API: GET /repos/{owner}/{repo}/comments/{comment_id}
  - Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}
      -  Receiver must scroll down to the desired comment on the
         page. 

### Notes
- Comment edits do not alter the identifier.
- Deletion or repository transfer is a platform-defined behavior
  but is **assumed not to occur** within the experimental scope.

---
