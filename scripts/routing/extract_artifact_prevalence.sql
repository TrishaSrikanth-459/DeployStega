/*
Routing Artifact Prevalence Extraction
Time window: June 1, 2025 → August 31, 2025
Data source: GH Archive (daily tables)

This query computes raw event counts by GitHub event type.
These counts are later mapped to routing artifact classes.
*/

-- ===============================
-- 1. Count all event types
-- ===============================
WITH event_counts AS (
    SELECT
        type AS event_type,
        COUNT(*) AS raw_count
    FROM `githubarchive.day.2025*`
    WHERE
        _TABLE_SUFFIX BETWEEN '0601' AND '0831'
    GROUP BY type
),

-- ===============================
-- 2. Compute total count
-- ===============================
total_count AS (
    SELECT
        SUM(raw_count) AS total_events
    FROM event_counts
)

-- ===============================
-- 3. Compute relative frequencies
-- ===============================
SELECT
    e.event_type,
    e.raw_count,
    SAFE_DIVIDE(e.raw_count, t.total_events) AS relative_frequency
FROM event_counts e
CROSS JOIN total_count t
ORDER BY e.raw_count DESC;
