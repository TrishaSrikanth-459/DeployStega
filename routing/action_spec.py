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
- Artifact classes MUST NOT implicitly access sibling artifact classes
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
                "Observe high-level repository structure without creating or modifying artifacts"
            ]
        ],
        "receiver": [
            [
                "Access the repository landing page",
                "Observe high-level repository structure without creating or modifying artifacts"
            ]
        ],
    },

    # ============================================================
    # Issue (container only — NO comments)
    # ============================================================

    "Issue": {
        "sender": [
            [
                "Access the specified issue page",
                "Click the issue edit control",
                "Modify mutable issue fields such as the title or body",
                "Save the updated issue contents"
            ],
        ],
        "receiver": [
            [
                "Access the specified issue page",
                "Read the issue title and body only",
                "Do not inspect or process issue comments"
            ]
        ],
    },

    # ============================================================
    # Pull Request (container only — NO comments)
    # ============================================================

    "PullRequest": {
        "sender": [
            [
                "Access the specified pull request page",
                "Edit the pull request title",
                "Save the modified title"
            ],
            [
                "Access the specified pull request page",
                "If a pull request description exists, edit the description; otherwise edit the title",
                "Save the modified content"
            ],
        ],
        "receiver": [
            [
                "Access the specified pull request page",
                "Read the pull request title and description only",
                "Do not inspect conversation comments or review comments"
            ]
        ],
    },

    # ============================================================
    # Commit (container only — NO comments)
    # ============================================================

    "Commit": {
        "sender": [],
        "receiver": [
            [
                "Access the specified commit page",
                "Review the commit diff and metadata representing the immutable snapshot",
                "Do not inspect or process commit comments"
            ]
        ],
    },

    # ============================================================
    # Issue Comment (comment-only surface)
    # ============================================================

    "IssueComment": {
        "sender": [
            [
                "Access the issue comment entry interface",
                "Create a new issue comment without modifying issue metadata",
                "Submit the comment"
            ],
            [
                "Access an existing issue comment",
                "Edit the comment contents only",
                "Save the updated comment"
            ],
            [
                "Access an existing issue comment",
                "Delete the comment",
                "Confirm the deletion"
            ],
        ],
        "receiver": [
            [
                "Access the issue comment region",
                "Iterate over visible issue comments only",
                "Attempt steganographic decoding on each comment"
            ]
        ],
    },

    # ============================================================
    # Pull Request Comment (comment-only surface)
    # ============================================================

    "PullRequestComment": {
        "sender": [
            [
                "Access the pull request conversation comment interface",
                "Create a new conversation comment",
                "Submit the comment"
            ],
            [
                "Access the pull request inline review interface",
                "Add a new inline review comment",
                "Submit the review comment"
            ],
            [
                "Access an existing pull request comment",
                "Edit the comment contents only",
                "Save the updated comment"
            ],
            [
                "Access an existing pull request comment",
                "Delete the comment",
                "Confirm the deletion"
            ],
        ],
        "receiver": [
            [
                "Access the pull request comment region",
                "Iterate over visible pull request comments only",
                "Attempt steganographic decoding on each comment"
            ]
        ],
    },

    # ============================================================
    # Commit Comment (comment-only surface)
    # ============================================================

    "CommitComment": {
        "sender": [
            [
                "Access the commit comment entry interface",
                "Create a new commit comment without modifying commit metadata",
                "Submit the comment"
            ],
            [
                "Access an existing commit comment",
                "Edit the comment contents only",
                "Save the updated comment"
            ],
            [
                "Access an existing commit comment",
                "Delete the comment",
                "Confirm the deletion"
            ],
        ],
        "receiver": [
            [
                "Access the commit comment region",
                "Iterate over visible commit comments only",
                "Attempt steganographic decoding on each comment"
            ]
        ],
    },
}
