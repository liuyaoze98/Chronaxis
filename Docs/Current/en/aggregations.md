# Result aggregation

Root `aggregations` summarizes calculation rows, events, window segments, or request/response results produced by one analysis. For example, first calculate mean power for each loaded interval, then calculate the P95 of the two means, 10 W and 20 W: 19.5 W. Each activity contributes one equally weighted row; activity duration is not used again as a weight. This feature does not load arbitrary historical CSV files or combine independent batch jobs.

## Run the complete example

[power-statistics.yaml](../examples/power-statistics.yaml) includes ASC input, signals, load rules, per-activity means, and aggregation. Run `chronaxis run power-statistics.yaml --output result-statistics` from its directory. Locate the aggregation table through this run's manifest outputs: load_mean_p95 is 19.5 W, with two candidates and two included values. [Complete actual results](example-results.md#power-statistics-yaml)

Replace the root aggregations section in that file with this excerpt; its calculations already defines load_mean:

```yaml
aggregations:                 # Summarize existing result rows
  - name: load_mean_p95       # Name of this new aggregate result
    source:                   # Select exactly one named result source
      calculation: load_mean  # Mean power for each loaded activity
    operation: quantile       # Quantile of those activity means
    q: 0.95                   # Probability for P95
```

## Choose a source and operation

| Sole field in source | Input rows | Allowed operations | Numeric field |
|---|---|---|---|
|calculation: name|Rows of a scalar calculation; select is not allowed|count, sum, mean, variance, quantile, median|Numeric operations infer value; field can be omitted|
|sequence: name|Discovered requests for this pairing rule|count, sum, mean, variance, quantile, median|Numeric operations use successful delay_ns values; field can be omitted|
|rule: name|Events of the named rule|count|Omit field|
|window: name|Final segments of the named window|count|Omit field|

count measures objects, not temporal coverage. Numeric operations use eligible rows. Confirmed timeouts and insufficient observation are counted separately; missing delays are never zero-filled.

## Fields and combinations

| Field | Type, requirement, and default | Meaning and constraints |
|---|---|---|
|name|Required unique name|Must not collide with other rule, window, calculation, or related node names|
|source|Required object|Exactly one field from the table above, naming a source within this analysis|
|operation|Required string|Choose from the source's operations; sum, mean, variance, quantile, or median summarize numeric values|
|field|Optional string|Only value for scalar calculations or delay_ns for numeric pairing aggregation; forbidden for count|
|group_by|String list; default []|[] makes one group; duplicate or unsupported keys are rejected|
|unit|Optional unit string|Source unit or a compatible target; variance squares the source unit; count accepts only 1|
|q|Finite number; required only for quantile|Inclusive range 0–1; P95 uses 0.95. Forbidden for other operations, including median|
|ddof|Integer; variance only, default 0|0 or 1; denominator N-ddof. Insufficient values produce no number; forbidden for other operations|
|include_partial|Boolean; default false|True is allowed only for numeric calculation aggregation and includes usable partial values; not for count or other sources|
|partial_policy|report or strict; inherits execution.partial_policy|report may return a partial known value; strict withholds the number when required data are incomplete|

Quantiles sort included values and interpolate at position `(N-1)×q`. Median fixes q=0.5. Exact quantiles retain the selected values and need sorting space within the analysis memory budget.

### Grouping keys

All sources allow dataset_id, entity_id, session_id, and their matching calculation_id, sequence_id, rule_id, or window_id. Per-event/per-window calculations also allow parent_id: the event or segment that produced that calculation row. A parent_id group exists only if its event or segment was actually produced. Session calculations cannot group by parent_id. Independent batch jobs form separate groups.

### Empty values and completeness

- With sufficient observation and no events, count for that event source is zero. A mean with no numeric values is empty, not zero.
- An event may exist while its mean's filter selects no samples. That empty mean cannot contribute zero. A complete zero integral or duration is a valid value and can participate.
- If the condition signal was interrupted, discovering three events does not prove that no events were missed during the gap. discovery_complete states whether observation is sufficient to identify all candidates; it is separate from each numeric result's completeness.
- Partial values are excluded by default. Enabling include_partial does not make missing, invalid, or insufficient-coverage values usable.

The output satisfies `candidate_count = included_count + definition_excluded_count + quality_excluded_count`. For five requests with four successful delays of 100, 200, 300, and 400 ms and one confirmed timeout, P95 is 385 ms: five candidates, four included, one excluded by definition. If observation ends before the last deadline, that request has insufficient observation instead of a confirmed timeout. [Output columns and statuses](results.md#v4-aggregations)
