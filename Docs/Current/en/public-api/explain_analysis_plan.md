# chronaxis.explain_analysis_plan

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.planning.reports.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-explain_analysis_plan"></a>
## `explain_analysis_plan`

List plan dependencies, node calculation methods, history requirements, and declared budgets.

```python
explain_analysis_plan(plan: AnalysisPlan) -> ExplainReport
```

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`plan`|[AnalysisPlan](AnalysisPlan.md#api-AnalysisPlan)|Yes|No default|Positional or keyword. A checked plan from `load_analysis_plan("analysis.yaml")` or `AnalysisPlan.from_dict(config)`, not a YAML filename string.|

Returns [ExplainReport](../../reference/chronaxis.planning.reports.md#api-ExplainReport) (Chinese implementation reference), including the same validation limits, dependency nodes, `history_ns`, a read-only budget mapping, and `requested_backend` / `selected_backend` / `backend_reason`. These last fields describe the request, static selection and reason; they are not measured timing. Existing numeric kernels and unsupported nodes are identified separately; the whole plan should not be assumed to execute as one array operation.

Raises `TypeError` if input is not an AnalysisPlan.

Processing expands derived, rule, window, and calculation dependencies, including conditions in event/window scopes. It reports the larger of original-signal validity and required window pre-history; it does not change the input reading range.

No execution/data-reading side effects and no measurement of peak memory.

```python
from chronaxis import load_analysis_plan, explain_analysis_plan
plan = load_analysis_plan("Docs/Current/examples/analysis.yaml")
print(explain_analysis_plan(plan))
```

## Source locations

- [`src/chronaxis/planning/reports.py:443`](../../../../src/chronaxis/planning/reports.py#L443) — line at `8904c2f744951857659abd40aaa3535d57faf53c`.
