# DeployStega Open Interaction Dataset  
**Specification and Research Usage Guide**

---

## 1. Purpose and Scope

The **DeployStega Open Interaction Dataset** is an interaction dataset designed to support empirical research on **covert communication mediated by large language models (LLMs)** under **behavioral, routing, and semantic adversaries**.

The dataset is motivated by the observation that, in realistic enterprise and platform deployments, adversaries primarily observe **application and platform logs** (e.g., audit logs, access telemetry, routing metadata), rather than direct access to message bodies. Accordingly, the dataset represents **adversary-visible interaction traces**, capturing *when*, *how*, and *which artifacts* users interact with, while supporting **explicit, auditable linkage to semantic content** through stable references.

The dataset enables rigorous evaluation of:

- **Behavioral-only adversaries** operating on interaction logs,
- **Semantic-only adversaries** operating on textual artifacts, and
- **Cross-layer adversaries** combining behavioral and semantic information.

The core research contribution is to demonstrate that **semantic-only steganalysis is suboptimal in realistic logging regimes**, and that **behavioral filtering can significantly reduce the cost of semantic inspection** by narrowing attention to a small subset of suspicious interactions.

---

## 2. Dataset Delivery Model

### 2.1 What external researchers receive

External researchers are provided with a **complete, static dataset release**. They are **not required to run any code** from the DeployStega repository in order to use the dataset.

The released dataset consists of **fully materialized data files**, described below, which can be loaded using standard JSON tooling.

---

## 3. Released Files and Directory Structure

A dataset release has the following structure:
```
deploystega_open_dataset/
├── interaction_dataset.jsonl
├── semantic_artifacts.jsonl
└── dataset_index.json
```

Each file has a precise and non-overlapping role.

---

## 4. interaction_dataset.jsonl (Interaction Logs)

### 4.1 File semantics

- Each line corresponds to exactly one user
- Each line contains a complete interaction trace
- Events are time-ordered
- Each trace has a mandatory label (benign or covert)

This file represents exactly what a behavioral adversary observes.

### 4.2 Event structure

Each event corresponds to a single interaction, analogous to an application log entry.
```json
{
  "timestamp": 1713456123.0,
  "action_type": "route_access",
  "artifact_ids": ["IssueComment", "repo_owner", "repo_name", 42],
  "metadata": {
    "artifact_class": "IssueComment",
    "role": "sender",
    "semantic_ref": "issue_42_body_v3"
  }
}
```

**Interpretation of artifact_ids:**

- `artifact_ids` is a structured identifier tuple
- Its interpretation depends on `artifact_class`
- Example: `["IssueComment", "repo_owner", "repo_name", 42]` uniquely identifies Issue #42.

### 4.3 Example trace (multiple events)
```json
{
  "label": "covert",
  "events": [
    {
      "timestamp": 1713456000,
      "action_type": "route_access",
      "artifact_ids": ["IssueComment", "repo", "example", 42],
      "metadata": {
        "artifact_class": "IssueComment",
        "role": "sender",
        "semantic_ref": "issue_42_body_v1"
      }
    },
    {
      "timestamp": 1713456120,
      "action_type": "route_access",
      "artifact_ids": ["IssueComment", "repo", "example", 42],
      "metadata": {
        "artifact_class": "IssueComment",
        "role": "receiver",
        "semantic_ref": "issue_42_body_v1"
      }
    }
  ]
}
```

---

## 5. semantic_artifacts.jsonl (Semantic Content)

### 5.1 Purpose

This file contains semantic artifacts referenced by interaction events. It enables semantic-only and cross-layer analysis.

### 5.2 File semantics

- Each line corresponds to exactly one semantic artifact, which corresponds to one event.
- Artifacts are referenced via `semantic_ref`
- Artifacts are explicitly labeled as benign or covert

### 5.3 Semantic artifact record format
```json
{
  "semantic_ref": "issue_42_body_v3",
  "artifact_class": "IssueComment",
  "artifact_ids": ["repo_owner", "repo_name", 42],
  "label": "covert",
  "content": "This is placeholder text containing steganographic payload. THIS WILL BE REPLACED.",
  "content_type": "text/plain"
}
```

---

## 6. dataset_index.json (Dataset Metadata)

This file provides dataset-level metadata required for reproducibility:
```json
{
  "num_users": 100,
  "num_traces": 100,
  "num_events": 4821,
  "labels": {
    "benign": 98,
    "covert": 2
  },
  "has_semantic_artifacts": true
}
```

---

## 7. Prescribed Research Use

External researchers should proceed as follows:

1. Load `interaction_dataset.jsonl` and `dataset_index.json` as a collection of user traces.

2. Compute behavioral and routing features using interaction logs only.

3. Train or evaluate behavioral detectors to flag suspicious traces or events.

4. Load `semantic_artifacts.jsonl` and join on `semantic_ref`.

5. Apply semantic analysis only to behaviorally flagged interactions.

6. Measure detection performance and semantic inspection cost reduction.

This workflow directly supports the dataset's intended contribution: **behavioral filtering as a cost-reduction mechanism for semantic steganalysis**.
