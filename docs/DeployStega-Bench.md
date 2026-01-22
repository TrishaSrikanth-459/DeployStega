# DeployStega-Bench
**Specification and Research Usage Guide**

---

## 1. Purpose and Scope

The **DeployStega-Bench** is a log-faithful interaction dataset designed to support empirical research on **covert communication mediated by large language models (LLMs)** under **behavioral, routing, and semantic adversaries**.

The dataset is motivated by the observation that, in realistic enterprise and platform deployments, adversaries primarily observe **application- and platform-level logs** (e.g., audit logs, access telemetry, routing metadata). Accordingly, the dataset represents **adversary-visible interaction traces**, capturing *when*, *how*, and *which artifacts* users interact with, while embedding **semantic content directly within interaction metadata** when available.

The dataset enables rigorous evaluation of:

- **Behavioral-only adversaries** operating exclusively on interaction logs,
- **Semantic-only adversaries** operating on textual content embedded in events, and
- **Cross-layer adversaries** combining behavioral and semantic information.

The core research contribution is to demonstrate that **semantic-only steganalysis is suboptimal in realistic logging regimes**, and that **behavioral filtering can significantly reduce the cost of semantic inspection** by narrowing attention to a small subset of suspicious interactions.

---

## 2. Dataset Delivery Model

### 2.1 What external researchers receive

External researchers are provided with a **complete, static dataset release**. They are **not required to run any code** from the DeployStega repository.

The released dataset consists of **fully materialized JSON files** that can be loaded using standard data-processing tools. All information required for behavioral, semantic, and cross-layer analysis is contained within the release.

---

## 3. Released Files and Directory Structure

A dataset release has the following structure:
```
deploystega_open_dataset/
├── interaction_dataset.jsonl
└── dataset_index.json
```

No additional semantic artifact files are required or provided. Semantic content, when present, is embedded directly within interaction events.

---

## 4. interaction_dataset.jsonl (Interaction Logs)

### 4.1 File semantics

- Each line corresponds to **exactly one user**
- Each line contains a **complete interaction trace**
- Events are **strictly time-ordered**
- Each trace has a **mandatory label** (`benign` or `covert`)
- Semantic content, if present, is embedded in event metadata

This file represents exactly what a behavioral adversary observes, augmented with semantic fields where available.

---

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
    "semantic_content": "This is placeholder semantic text. THIS WILL BE REPLACED."
  }
}
```

**Interpretation of artifact_ids:**

- `artifact_ids` is a structured, stable identifier tuple
- The first element is the artifact class
- Remaining elements uniquely identify the artifact instance
- Example: `["IssueComment", "repo_owner", "repo_name", 42]` uniquely identifies Issue #42 in the repository

---

### 4.3 Example trace with multiple events

Each line in `interaction_dataset.jsonl` represents a single user trace:
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
        "semantic_content": "Covert placeholder payload. TO BE REPLACED."
      }
    },
    {
      "timestamp": 1713456120,
      "action_type": "route_access",
      "artifact_ids": ["IssueComment", "repo", "example", 42],
      "metadata": {
        "artifact_class": "IssueComment",
        "role": "receiver",
        "semantic_content": "Same artifact viewed by receiver."
      }
    }
  ]
}
```

This structure mirrors realistic application logs while preserving sufficient structure for behavioral and semantic analysis.

---

## 5. Semantic Content: Representation and Rationale

### 5.1 Embedded semantic content

Semantic content is embedded directly within the `metadata` field of interaction events, under the key `semantic_content`.

This design reflects scenarios in which adversaries may observe textual content (e.g., comments, commit messages, issue bodies) through logs, snapshots, or audit trails.

---

## 6. dataset_index.json (Dataset Metadata)

The `dataset_index.json` file provides dataset-level metadata required for reproducibility and evaluation.

**Example:**
```json
{
  "format_version": 1,
  "output_files": {
    "interaction_dataset": "interaction_dataset.jsonl",
    "dataset_index": "dataset_index.json"
  },
  "num_users": 2,
  "num_events": 5,
  "user_labels": {
    "0": "covert",
    "1": "benign"
  },
  "label_counts": {
    "benign": 1,
    "covert": 1
  },
  "label_schema": {
    "benign": "No covert communication is present in this user's trace.",
    "covert": "This user's trace contains covert activity by design (ground truth)."
  }
}
```

Labels are explicit, mandatory, and unambiguous.

---

## 7. Prescribed Research Use

External researchers should proceed as follows:

1. Load `interaction_dataset.jsonl` and treat each line as a single user trace.

2. Compute behavioral and routing features using interaction logs.

3. Train or evaluate behavioral detectors to flag suspicious traces or events.

4. Apply semantic analysis to embedded semantic fields only for behaviorally flagged interactions.

5. Measure detection performance and semantic inspection cost reduction.

This workflow directly supports the dataset's intended contribution: **behavioral filtering as a principled cost-reduction mechanism for semantic steganalysis**.
