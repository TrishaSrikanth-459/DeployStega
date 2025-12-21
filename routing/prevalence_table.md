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

### Observation Window

All counts are computed over a fixed, explicitly defined time window:

- **Start time**: `<YYYY-MM-DD>`
- **End time**: `<YYYY-MM-DD>`

Only access events occurring within this window are included.

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
| `<ClassName1>` | `<count>` | `<fraction>`       | `<optional>` |
| `<ClassName2>` | `<count>` | `<fraction>`       | `<optional>` |
| `<ClassName3>` | `<count>` | `<fraction>`       | `<optional>` |
| …              | …         | …                  | … |

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

yaml
Copy code

Relative frequencies sum to 1.0 across all artifact classes.

### Notes (optional)
Dataset-specific caveats, anomalies, or interpretation notes.

---

## Normalization Procedure

Let:

Total = Σ (raw counts across all artifact classes)

perl
Copy code

For each artifact class:

relative_frequency = raw_count / Total

yaml
Copy code

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
