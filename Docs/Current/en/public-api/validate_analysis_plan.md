# chronaxis.validate_analysis_plan

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.planning.reports.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-validate_analysis_plan"></a>
## `validate_analysis_plan`

Report static configuration validity and the currently supported reading, execution, and publication capabilities.

```python
validate_analysis_plan(plan: AnalysisPlan) -> ValidationReport
```

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`plan`|[AnalysisPlan](AnalysisPlan.md#api-AnalysisPlan)|Yes|No default|Positional or keyword. A checked plan from `load_analysis_plan("analysis.yaml")` or `AnalysisPlan.from_dict(config)`, not a YAML filename string.|

Returns [ValidationReport](../../reference/chronaxis.planning.reports.md#api-ValidationReport) (Chinese implementation reference). A valid, supported plan has `valid=True` and empty `errors`. `warnings` retains unverified fields, observation ranges, and unit status; `capability_status` describes available execution support. `execution_ready` reflects static capability errors, not proof of data being read or adequate real RAM.

Raises `TypeError` when input is not an AnalysisPlan (message: “validate_analysis_plan需要AnalysisPlan。”). Configuration construction errors are reported by the construction entry point first.

No source-reading side effects. Does not recheck CSV, BLF/DBC, actual fields, or physical measurement meanings.

```python
from chronaxis import load_analysis_plan, validate_analysis_plan
plan = load_analysis_plan("Docs/Current/examples/analysis.yaml")
report = validate_analysis_plan(plan)
print(report.valid, report.execution_ready)
```

## Source locations

- [`src/chronaxis/planning/reports.py:282`](../../../../src/chronaxis/planning/reports.py#L282) — line at `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`.
