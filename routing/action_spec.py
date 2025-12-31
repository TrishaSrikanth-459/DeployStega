"""
action_spec.py

Defines role-specific, identifier-preserving actions for each artifact class
as specified by the DeployStega routing namespace.

IMPORTANT INVARIANTS:
- This module NEVER emits URLs
- This module NEVER constructs or templates addresses
- The resolver provides exactly one concrete URL
- These steps describe what the user must do AFTER visiting that URL
- Descriptions are NOT condensed from the routing namespace
"""

from typing import Dict, List


ACTION_SPECS: Dict[str, Dict[str, List[List[str]]]] = {

    # ============================================================
    # Repository
    # ============================================================

    "Repository": {
        "sender": [
            [
                "Retrieve the specified GitHub repository",
                "Observe the repository contents, including source code, issues, pull requests, commits, and related collaborative artifacts"
            ]
        ],
        "receiver": [
            [
                "Retrieve the specified GitHub repository",
                "Observe the repository contents, including source code, issues, pull requests, commits, and related collaborative artifacts"
            ]
        ],
    },

    # ============================================================
    # Issue
    # ============================================================

    "Issue": {
        "sender": [
            [
                "Create a new issue associated with the repository",
                "Enter a title describing the tracked unit of work, discussion, or bug report",
                "Enter a detailed issue description",
                "Submit the issue"
            ],
            [
                "Access an existing issue within the repository",
                "Click the edit control for the issue",
                "Modify mutable issue fields such as the title or body",
                "Save the updated issue contents"
            ],
        ],
        "receiver": [
            [
                "Access the specified issue within the repository",
                "Read the issue title and description"
            ]
        ],
    },

    # ============================================================
    # Pull Request
    # ============================================================

    "PullRequest": {
        "sender": [
            [
                "Initiate the creation of a pull request proposing changes from a source branch into a target branch",
                "Provide a pull request title",
                "Provide a pull request description",
                "Submit the pull request"
            ],
            [
                "Access the existing pull request",
                "Edit the pull request title",
                "Save the modified title"
            ],
            [
                "Access the existing pull request",
                "Edit the pull request body description",
                "Save the modified description"
            ],
            [
                "Access the existing pull request",
                "Merge the pull request into the target branch",
                "Enter a commit message and extended description",
                "Confirm the merge operation"
            ],
        ],
        "receiver": [
            [
                "Access the specified pull request",
                "Read the pull request description",
                "Review the discussion and associated changes"
            ]
        ],
    },

    # ============================================================
    # Commit
    # ============================================================

    "Commit": {
        "sender": [
            [
                "Edit an existing file within the repository",
                "Modify the file contents",
                "Commit the changes, producing a new immutable snapshot of repository state"
            ],
            [
                "Create a new file within the repository",
                "Enter the contents for the new file",
                "Commit the changes, producing a new immutable snapshot of repository state"
            ],
        ],
        "receiver": [
            [
                "Access the specified commit",
                "Review the commit diff representing the immutable snapshot of repository state",
                "Read any associated commit comments"
            ]
        ],
    },

    # ============================================================
    # Issue Comment
    # ============================================================

    "IssueComment": {
        "sender": [
            [
                "Access the specified issue",
                "Enter a new comment associated with the issue",
                "Submit the comment"
            ],
            [
                "Access the specified issue",
                "Edit an existing issue comment",
                "Update the comment contents"
            ],
            [
                "Access the specified issue",
                "Delete an existing issue comment",
                "Confirm the deletion"
            ],
        ],
        "receiver": [
            [
                "Access the specified issue",
                "Scroll to the issue comments",
                "Read the specified comment"
            ]
        ],
    },

    # ============================================================
    # Pull Request Comment
    # ============================================================

    "PullRequestComment": {
        "sender": [
            [
                "Access the pull request conversation",
                "Enter a new conversation comment",
                "Submit the comment"
            ],
            [
                "Access the pull request file changes",
                "Add a new inline review comment associated with a specific change",
                "Submit the review comment"
            ],
            [
                "Access an existing pull request comment",
                "Edit the comment contents",
                "Update the comment"
            ],
            [
                "Access an existing pull request comment",
                "Delete the comment",
                "Confirm the deletion"
            ],
        ],
        "receiver": [
            [
                "Access the pull request conversation",
                "Scroll through the conversation comments"
            ],
            [
                "Access the pull request file changes",
                "Scroll through the inline review comments"
            ],
        ],
    },

    # ============================================================
    # Commit Comment
    # ============================================================

    "CommitComment": {
        "sender": [
            [
                "Access the specified commit",
                "Enter a new comment associated with the commit",
                "Submit the comment"
            ],
            [
                "Access the specified commit",
                "Edit an existing commit comment",
                "Update the comment contents"
            ],
            [
                "Access the specified commit",
                "Delete an existing commit comment",
                "Confirm the deletion"
            ],
        ],
        "receiver": [
            [
                "Access the specified commit",
                "Scroll to the commit comments",
                "Read the specified comment"
            ]
        ],
    },
}
