# Routing Namespace and Identifier Schemas

## Overview
This document defines the complete routing namespace used by DeployStega.
The routing namespace enumerates all addressable artifact classes exposed
by the application and specifies their identifier schemas.

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
#### Retrieves the specified repository
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
#### Modifies mutable fields of an existing issue
  - REST API: PATCH /repos/{owner}/{repo}/issues/{issue_number}
  - Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}
      - Upon visiting this url, the sender must click the "edit" button on the top right.

### Addressability (Sender and Receiver)
#### Access specific issues
  - REST API: GET /repos/{owner}/{repo}/issues/{issue_number}
  - Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}

### Notes
- Editing issue fields (body, labels, assignees, lock state, open/closed)
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
#### Modifies mutable pull request fields
   - REST API: PATCH /repos/{owner}/{repo}/pulls/{pull_number}
   - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}
       - Upon visiting the URL, the sender must or click "..." and then "Edit" near the top right of the pull request's body to edit the body.

### Addressability (Sender and Receiver)
#### View an existing pull request. 
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
- branch: string
- commit_sha: hexadecimal hash

### Identifier Construction Rule
A commit is uniquely identified by the ordered tuple
(owner, repo, branch, commit_sha), where:
- owner: The GitHub user or organization that owns the repository.
- repo: The repository name in which the commit exists.
- branch: The branch that refers to specific commits
- commit_sha: The cryptographic hash that uniquely identifies the commit.

### Addressability (Sender and Receiver)
#### Access specified commits
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
#### Create an issue comment
   - REST API: POST /repos/{owner}/{repo}/issues/{issue_number}/comments
   - Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}
       - Sender must enter the comment's content in the text box under "Add a comment" and subsequently click "comment" to save their changes.
#### Edit an existing issue comment
   - REST API: PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}
   - Web URL: https://github.com/{owner}/{repo}/issues/{issue_number}
       - Sender must click "..." near the top-right of the comment's textbox, click "Edit," enter the comment's content, and finally, click "Update comment."
         
### Addressability (Sender and Receiver) 
#### Access specified issue comments
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
#### Create a new pull request review comment
   - REST API: POST /repos/{owner}/{repo}/pulls/{pull_number}/comments
   - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}/files
       - Sender must hover over "+" to the left of the specific change they wish to comment on, enter the comment's contents in the newly appeared text box, and finally, click "Add review comment."
#### Reply to an existing pull request review comment
   - REST API: POST /repos/{owner}/{repo}/pulls/{pull_number}/comments/{comment_id}/replies
   - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}/files
       - Sender must enter the reply's comments in the textbox underneath the comment they wish to reply to, and finally, click "Add review comment."
#### Edit an existing pull request review comment
   - REST API: PATCH /repos/{owner}/{repo}/pulls/comments/{comment_id}
   - Web URL: https://github.com/{owner}/{repo}/pull/{pull_number}/files
       - Sender must click "..." near the top right of the text box of the comment, click "Edit," enter the desired edits in the newly appeared text box, and finally, click "Update comment."
         
### Addressability (Sender and Receiver)
#### Access specified pull request review comments
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
#### Create a new commit comment 
  - REST API: POST /repos/{owner}/{repo}/commits/{commit_sha}/comments
  - Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}
      - Sender must scroll to the bottom of the commit page (or to a specific line in the diff view),
        enter comment text into the comment input box, and click **“Comment”**.
#### Edit an existing commit comment
   - REST API: PATCH /repos/{owner}/{repo}/comments/{comment_id}
   - Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}
       - Sender must click "..." near the top right of the comment's text box, click "Edit," enter the desired edits, and finally, click "Update comment." They may do so for either a general comment or a line-specific comment.
         
### Addressability (Sender and Receiver)
#### Access specified commit comments
   - REST API: GET /repos/{owner}/{repo}/comments/{comment_id}
   - Web URL: https://github.com/{owner}/{repo}/commit/{commit_sha}
       - Receiver must scroll down to the desired comment on the page.

### Notes
- Comment editing does not alter the identifier.
- Identifier-changing operations such as repository transfer are
  **assumed not to occur** within the experimental scope.

---

## Artifact Class: GitTag

### Description
Git tags are **immutable, named pointers** to particular repository states.
Tag visibility via the GUI is **near-immediate** after creation.
A release is a user-curated wrapper around a tag that presents a specific repository state as a named, documented distribution.

### Identifier Fields
- owner: string  
- repo: string  
- tag: string

### Identifier Construction Rule
A GitTag is uniquely identified by the ordered tuple
(owner, repo, tag).

### Addressability (Sender)
#### Edit an existing tag's description or associated assets
   - URL: https://github.com/{owner}/{repo}/releases/tag/{tag}
       - Sender may edit the description as weell as upload relevant files before finally clicking "update release." 

### Addressability (Sender and Receiver)
#### View the title, description, and assets associated with a specific tag
  - REST API: get /repos/{owner}/{repo}/git/tags/{tag_sha}
  - URL: https://github.com/{owner}/{repo}/releases/tag/{tag}

### Notes
- Tag editing does not alter the identifier.
- Identifier-changing operations such as the creation of new tags or the deletion of existing tags are
  **assumed not to occur** within the experimental scope.

---

## Artifact Class: Label

### Description
Labels are **named, repository-defined identifiers** used to categorize and organize issues and pull requests.  

### Identifier Fields
- owner: string  
- repo: string  
- label_name: string

### Identifier Construction Rule
A Label is uniquely identified by the ordered tuple
(owner, repo, label_name).

### Addressability (Sender)
#### Edit a particular label
  - REST API: patch /repos/{owner}/{repo}/labels/{name}
  - URL: https://github.com/{owner}/{repo}/labels
    - Scroll down to the particular label, click "...," click "edit," update the "Description" as desired, and finally, click "Save changes."

### Addressability (Sender and Receiver)
#### View a specific label
  - REST API: get /repos/{owner}/{repo}/labels/{name}
  - URL: https://github.com/{owner}/{repo}/issues?q=state%3Aopen%20label%3A%22{label_name}%22
    - If the label name includes spaces, replace them with "%20" 

### Notes
- Creating or deleting labels constitute **snapshot-mutating actions** and are therefore out of scope.
- More query filtering and/or sorting, with the exception of querying for specific labels, are considered **presentation-layer variations**.

 ---

## Artifact Class: Milestone

### Description
A milestone is a **named planning artifact** used to group issues and pull requests around a target goal or deadline.  

### Identifier Fields
- owner: string  
- repo: string  
- milestone_number: integer  

### Identifier Construction Rule
A Milestone is uniquely identified by the ordered tuple
(owner, repo, milestone_number).

### Addressability (Sender)
#### Update milestone metadata (description, due date, state)
  - REST API: patch/repos/{owner}/{repo}/milestones/{milestone_number}
  - URL: https://github.com/{owner}/{repo}/milestones/{milestone_number}/edit
    - Sender may edit the "Due Date (options)" and/or "Description (options)" before, finally, clicking "Save changes." 

### Addressability (Sender and Receiver)
#### View a specific milestone
  - REST API: get /repos/{owner}/{repo}/milestones/{milestone_number}
  - URL: https://github.com/{owner}/{repo}/milestone/{milestone_number}
    - Shows milestone metadata and the list of associated issues and pull requests.

### Notes 
- Milestone visibility and updates are **reflected immediately** in the GitHub GUI.
- Milestones may exist in `open` or `closed` states; such states are not modeled in the experiment.
- Further sorting, filtering, and pagination indicators are treated as **presentation-layer variations** and are not modeled as independent interactions.
- Identifier-changing operations such as the creation of new milestones or the closure/deletion of existing milestones are
  **assumed not to occur** within the experimental scope.

---
