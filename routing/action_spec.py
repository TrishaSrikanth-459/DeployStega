"""
action_spec.py

Defines role-specific, identifier-preserving actions for each artifact class
as specified by the DeployStega routing namespace.

IMPORTANT INVARIANTS:
- This module NEVER emits URLs
- This module NEVER constructs or templates addresses
- The resolver provides exactly one concrete URL
- These steps describe what the user must do AFTER visiting that URL
- ALL actions are identifier-preserving
- NO action may create new identifiers not present in the snapshot
"""

from typing import Dict, List


ACTION_SPECS: Dict[str, Dict[str, List[List[str]]]] = {

    # ============================================================
    # Repository
    # ============================================================

    "Repository": {
        "sender": [
            [
                "Access the repository landing page",
                "Observe repository contents without creating or modifying artifacts"
            ]
        ],
        "receiver": [
            [
                "Access the repository landing page",
                "Observe repository contents without creating or modifying artifacts"
            ]
        ],
    },

    # ============================================================
    # Issue (identifier-preserving only)
    # ============================================================

    "Issue": {
        "sender": [
            [
                "Access the specified issue within the repository",
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
    # Pull Request (identifier-preserving only)
    # ============================================================

    "PullRequest": {
        "sender": [
            [
                "Access the existing pull request",
                "Edit the pull request title",
                "Save the modified title"
            ],
            [
                "Access the existing pull request",
                "If a pull request description exists, edit the description; otherwise edit the title",
                "Save the modified content"
            ],
        ],
        "receiver": [
            [
                "Access the specified pull request",
                "Read the pull request description and title",
                "Review the discussion and associated changes"
            ]
        ],
    },

    # ============================================================
    # Commit (receiver-only)
    # ============================================================

    "Commit": {
        "sender": [],
        "receiver": [
            [
                "Access the specified commit",
                "Review the commit diff representing the immutable snapshot of repository state",
                "Read any associated commit comments"
            ]
        ],
    },

    # ============================================================
    # Issue Comment (container-level)
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
                "Scroll through all visible issue comments",
                "Attempt steganographic decoding on each comment"
            ]
        ],
    },

    # ============================================================
    # Pull Request Comment (container-level)
    # ============================================================

    "PullRequestComment": {
        "sender": [
            [
                "Access the pull request conversation view",
                "Enter a new conversation comment",
                "Submit the comment"
            ],
            [
                "Access the pull request file changes view",
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
                "Access the pull request conversation view",
                "Scroll through all visible conversation comments"
            ],
            [
                "Access the pull request file changes view",
                "Scroll through all visible inline review comments"
            ],
        ],
    },

    # ============================================================
    # Commit Comment (container-level)
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
                "Scroll through all visible commit comments",
                "Attempt steganographic decoding on each comment"
            ]
        ],
    },
}
