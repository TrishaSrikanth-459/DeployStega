# Routing Artifact Prevalence Table

## Overview

This document reports the marginal prevalence of each artifact class in the
routing namespace, measured over benign GitHub interaction logs.

Prevalence is defined as **raw access-event counts per artifact class** within a
specified observation window. These statistics characterize how frequently
different artifact classes are *accessed* in normal platform activity and do
not encode behavioral structure, user intent, or routing paths.

This document is **structural and population-level**. It does not assess
whether specific users behave suspiciously.

---

## Measurement Definition

### Time Window Selection

Artifact prevalence statistics are computed over a fixed, closed historical
window rather than a rolling or real-time interval.

**Time window:** June 1, 2025 → July 1, 2025

This window was chosen to satisfy the following criteria:

- It reflects contemporary GitHub usage patterns relevant to modern
  collaborative development workflows.
- The interval is fully completed, avoiding partial ingestion, delayed
  event reporting, or incomplete hourly archives.
- The one-month duration is sufficient to smooth short-term fluctuations
  in activity while remaining focused on structural artifact prevalence
  rather than long-term platform evolution.
- Using a fixed historical window ensures reproducibility and prevents
  confounding effects from ongoing platform changes or measurement drift.

The purpose of this window is not to model temporal trends or seasonality,
but to establish a representative baseline for the **marginal frequency of
artifact access events** in benign platform logs. These prevalence estimates
characterize what artifacts are commonly accessed under normal conditions
and provide empirical grounding for the routing namespace.

---

### Unit of Measurement

Each count corresponds to a **single logged access event** referencing an
artifact instance in benign platform logs.

An *access event* is defined as:

- A recorded interaction in the source dataset indicating that a user viewed,
  fetched, or otherwise referenced an artifact instance.
- The exact logging mechanism depends on the data source and is documented
  alongside the counting procedure.

---

### Counting Semantics

- Each access event is counted independently.
- Multiple accesses to the same artifact by the **same user** are counted
  separately.
- Accesses to the same artifact by **different users** are also counted
  separately.
- No aggregation or normalization is performed at the user level.

This document intentionally does **not** distinguish access events by user
identity.

User-level repetition, concentration, or deviation from baseline behavior is
modeled separately through behavioral feature extraction and adversarial
analysis.

---

### Included Artifacts

- Only artifact classes defined in the routing namespace are counted.
- No other platform objects, metadata fields, or derived entities are included.

---

## Data Sources

- **Primary sources**:
  - `GH Archive`
  - `GHTorrent`

- **Dataset version(s)**:
  - `<Version identifier / snapshot date>`

- **Population scope**:
  - `<e.g., public repositories only / collaborator activity / all users>`

---

## Artifact Prevalence Table

| Artifact Class | Raw Count | Relative Frequency | Notes |
|----------------|-----------|--------------------|-------|
| `Repository` | `<count>` | `<fraction>`       | `<optional>` |
| `Issue` | `<count>` | `<fraction>`       | `<optional>` |
| `PullRequest` | `<count>` | `<fraction>`       | `<optional>` |
| `Commit` | `<count>` | `<fraction>`       | `<optional>` |
| `IssueComment` | `<count>` | `<fraction>`       | `<optional>` |
| `PullRequestReviewComment` | `<count>` | `<fraction>`       | `<optional>` |
| `CommitComment` | `<count>` | `<fraction>`       | `<optional>` |

--- 

## Column Definitions

### Artifact Class
Name of the artifact class as defined in the routing namespace.

### Raw Count
Total number of logged access events referencing artifacts of this class within
the observation window.

### Relative Frequency
Normalized prevalence computed as:

raw_count / total_raw_count_across_all_classes

Relative frequencies sum to 1.0 across all artifact classes.

### Notes (optional)
Dataset-specific caveats, anomalies, or interpretation notes.

---

## Normalization Procedure

Let:

Total = Σ (raw counts across all artifact classes)

For each artifact class:

relative_frequency = raw_count / Total

---

## Intended Use

The prevalence table is used to:

- Characterize realism and coverage of the routing namespace
- Inform discussion of artifact selection bias
- Support sensitivity and ablation analyses
- Provide empirical grounding for routing assumptions

These values are **not** used to:
- train behavioral models
- enforce feasibility constraints
- detect covert communication

---

## Limitations

- Counts depend on dataset coverage, logging granularity, and sampling window.
- Rare artifact classes may be underrepresented.
- Results may not generalize across platforms, repositories, or time periods.

---

## Reproducibility

- Raw counts are derived from:
  - `data/derived/routing_prevalence/artifact_counts.csv`
- Relative frequencies are derived from:
  - `data/derived/routing_prevalence/artifact_frequencies.csv`

Any scripts used for counting are documented separately

---

## Change Log

- `<Date>` — Template created
- `<Date>` — Counts populated
- `<Date>` — Dataset version updated
