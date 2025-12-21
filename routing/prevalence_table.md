# Routing Artifact Prevalence Table

## Overview

This document reports the marginal prevalence of each artifact class in the
routing namespace, measured over benign GitHub interaction logs.

Prevalence is defined as **raw access counts per artifact class**, without
considering ordering, timing, transitions, or sender–receiver relationships.
These statistics characterize how frequently different artifact classes appear
in normal platform activity and do not encode behavioral structure.

---

## Measurement Definition

### Unit of Measurement

Each count corresponds to a single observed access or reference to an artifact
instance in benign platform logs.

The exact interpretation of an “access” depends on the source dataset and is
documented alongside the counting procedure.

### Included Artifacts

Only artifact classes defined in the routing namespace are counted. No other
platform objects or metadata fields are included.

---

## Data Sources

- **Primary sources**:
  - `<DataSourceName1>` (e.g., GH Archive)
  - `<DataSourceName2>` (e.g., GHTorrent)

- **Dataset version(s)**:
  - `<Version / snapshot date>`

- **Time window**:
  - `<Start date>` → `<End date>`

- **Population scope**:
  - `<e.g., public repositories / collaborator activity / all users>`

---

## Artifact Prevalence Table

| Artifact Class | Raw Count | Relative Frequency | Notes |
|----------------|-----------|--------------------|-------|
| `<ClassName1>` | `<count>` | `<fraction>`       | `<optional>` |
| `<ClassName2>` | `<count>` | `<fraction>`       | `<optional>` |
| `<ClassName3>` | `<count>` | `<fraction>`       | `<optional>` |
| …              | …         | …                  | … |

### Column Definitions

- **Artifact Class**  
  Name of the artifact class as defined in the routing namespace.

- **Raw Count**  
  Total number of observed accesses for this artifact class.

- **Relative Frequency**  
  Normalized frequency computed as:

class_raw_count / total_raw_count_across_all_classes

yaml
Copy code

- **Notes** (optional)  
Any caveats, anomalies, or dataset-specific observations.

---

## Normalization Procedure

- Let:

Total = Σ (raw counts across all artifact classes)

vbnet
Copy code

- Relative frequency for each class is computed as:

raw_count / Total

yaml
Copy code

- Relative frequencies sum to 1.0 across all classes.

---

## Interpretation Constraints

- These counts represent **marginal prevalence only**.
- No information is captured about:
- access order
- timing
- sessions
- correlations
- routing paths
- Prevalence statistics are **not routing rules** and do not constrain
sender or receiver behavior directly.

---

## Intended Use

The prevalence table is used to:

- Characterize realism of the routing namespace
- Inform discussion of artifact selection bias
- Support sensitivity and ablation analyses
- Provide empirical grounding for routing assumptions

These values are **not** used to train behavioral models or enforce feasibility
constraints.

---

## Limitations

- Counts depend on:
- dataset coverage
- logging granularity
- sampling window
- Rare artifact classes may be underrepresented.
- Results may not generalize across time periods or repository populations.

---

## Reproducibility

- Raw counts are derived from:
- `data/derived/routing_prevalence/artifact_counts.csv`
- Relative frequencies are derived from:
- `data/derived/routing_prevalence/artifact_frequencies.csv`

- Any scripts used for counting are documented separately and do not implement
routing logic or behavioral assumptions.

---

## Change Log

- `<Date>` — Initial template created
- `<Date>` — Counts populated
- `<Date>` — Dataset version updated
