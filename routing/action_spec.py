"""
action_spec.py

Defines role-specific, identifier-preserving actions for each artifact class as specified by
the DeployStega routing namespace + benign interaction namespace.

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
    # Routing / mutative namespace
    # ============================================================

    "Repository": {
        "sender": [[
            "Access the repository landing page",
            "Observe high-level repository structure without creating or modifying artifacts",
        ]],
        "receiver": [[
            "Access the repository landing page",
            "Observe high-level repository structure without creating or modifying artifacts",
            "Do not attempt steganographic decoding yet",
        ]],
    },

    "Issue": {
        "sender": [[
            "Access the specified issue page",
            "Click the issue edit control",
            "Modify the issue's body",
            "Save the updated issue contents",
        ]],
        "receiver": [[
            "Access the specified issue page",
            "Attempt steganographic decoding on the issue body",
            "Do not process issue comments",
        ]],
    },

    "PullRequest": {
        "sender": [[
            "Access the specified pull request page",
            "Edit the pull request description",
            "Save the modified content",
        ]],
        "receiver": [[
            "Access the specified pull request page",
            "Attempt steganographic decoding on the pull request description",
            "Do not process conversation comments or review comments",
        ]],
    },

    "Commit": {
        "sender": [],
        "receiver": [[
            "Access the specified commit page",
            "Review the commit diff and metadata",
            "Do not attempt steganographic decoding yet",
        ]],
    },

    "IssueComment": {
        "sender": [
            [
                "Access the issue comment entry interface",
                "Create a new issue comment",
                "Submit the comment",
            ],
            [
                "Access an existing issue comment",
                "Edit the comment contents only",
                "Save the updated comment",
            ],
        ],
        "receiver": [[
            "Access the issue comment region",
            "Iterate over visible issue comments",
            "Attempt steganographic decoding on each comment",
        ]],
    },

    "PullRequestComment": {
        "sender": [
            [
                "Access the pull request conversation comment interface",
                "Create a new conversation comment",
                "Submit the comment",
            ],
            [
                "Access the pull request inline review interface",
                "Add a new inline review comment",
                "Submit the review comment",
            ],
            [
                "Access an existing pull request comment",
                "Edit the comment contents only",
                "Save the updated comment",
            ],
        ],
        "receiver": [[
            "Access the pull request comment region",
            "Iterate over visible pull request comments",
            "Attempt steganographic decoding on each comment",
        ]],
    },

    "CommitComment": {
        "sender": [
            [
                "Access the commit comment entry interface",
                "Create a new commit comment",
                "Submit the comment",
            ],
            [
                "Access an existing commit comment",
                "Edit the comment contents only",
                "Save the updated comment",
            ],
        ],
        "receiver": [[
            "Access the commit comment region",
            "Iterate over visible commit comments only",
            "Attempt steganographic decoding on each comment",
        ]],
    },

    # ============================================================
    # NEW: GitTag
    # ============================================================

    "GitTag": {
        "sender": [[
            "Access the specified tag or release page",
            "Edit the tag or release description",
            "Optionally upload or update associated assets",
            "Save the updated release contents",
        ]],
        "receiver": [[
            "Access the specified tag or release page",
            "View the tag title, description, and associated assets",
            "Attempt steganographic decoding on the tag description",
        ]],
    },

    # ============================================================
    # NEW: Label
    # ============================================================

    "Label": {
        "sender": [[
            "Access the repository labels page",
            "Locate the specified label",
            "Edit the label description",
            "Save the updated label metadata",
        ]],
        "receiver": [[
            "Access the issues view filtered by the specified label",
            "View the label name and description",
            "Attempt steganographic decoding on the label description",
        ]],
    },

    # ============================================================
    # NEW: Milestone
    # ============================================================

    "Milestone": {
        "sender": [[
            "Access the specified milestone edit page",
            "Update the milestone description or due date",
            "Save the updated milestone metadata",
        ]],
        "receiver": [[
            "Access the specified milestone page",
            "View the milestone description and associated issues or pull requests",
            "Attempt steganographic decoding on the milestone description",
        ]],
    },

    # ============================================================
    # Benign interaction namespace (observational-only)
    # ============================================================

    "Notifications_Benign": {
        "sender": [[
            "Access the notifications view scoped to the repository",
            "Do not mark threads read/unread or change subscription state",
            "Treat this as a benign baseline visit",
        ]],
        "receiver": [[
            "Access the notifications view scoped to the repository",
            "Do not rely on notifications existing (existence is not modeled)",
            "Treat this as a benign baseline visit",
        ]],
    },

    "Events_Benign": {
        "sender": [[
            "Access the repository activity (events) page",
            "Do not apply filters as a distinct modeled interaction",
            "Treat this as a benign baseline visit",
        ]],
        "receiver": [[
            "Access the repository activity (events) page",
            "Do not assume any event exists at this time (existence is not modeled)",
            "Treat this as a benign baseline visit",
        ]],
    },

    "Starring_Benign": {
        "sender": [[
            "Access the repository stargazers page",
            "Do not star/unstar the repository",
            "Treat this as a benign baseline visit",
        ]],
        "receiver": [[
            "Access the repository stargazers page",
            "Do not infer star state changes (not modeled here)",
            "Treat this as a benign baseline visit",
        ]],
    },

    "Watching_Benign": {
        "sender": [[
            "Access the repository watchers or subscribers page",
            "Do not change watching or subscription state",
            "Treat this as a benign baseline visit",
        ]],
        "receiver": [[
            "Access the repository watchers or subscribers page",
            "Do not change watching or subscription state",
            "Treat this as a benign baseline visit",
        ]],
    },

    "Branches_Benign": {
        "sender": [[
            "Access the repository branches listing page",
            "Do not create, rename, or delete branches",
            "Treat this as a benign baseline visit",
        ]],
        "receiver": [[
            "Access the repository branches listing page",
            "Do not create, rename, or delete branches",
            "Treat this as a benign baseline visit",
        ]],
    },

    "Branch_Benign": {
        "sender": [[
            "Access the specified branch page",
            "Do not create, rename, or delete branches or modify protections",
            "Treat this as a benign baseline visit",
        ]],
        "receiver": [[
            "Access the specified branch page",
            "Do not create, rename, or delete branches or modify protections",
            "Treat this as a benign baseline visit",
        ]],
    },

    "Commits_Benign": {
        "sender": [[
            "Access the commits list page for the specified branch",
            "Do not attempt to create commits or push changes",
            "Treat this as a benign baseline visit",
        ]],
        "receiver": [[
            "Access the commits list page for the specified branch",
            "Treat this as benign baseline browsing of history",
            "Do not attempt decoding from this page unless explicitly added later",
        ]],
    },
}
