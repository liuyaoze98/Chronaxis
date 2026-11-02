# chronaxis.AnalysisRunner

Import this object from `chronaxis`. This page lists direct public members and necessary construction/context protocols. See the [module reference](../../reference/chronaxis.runner.md) for internal implementation (Chinese implementation reference).

Return to the [public API index](../api.md). Linked parameter types lead to their definitions. Check required fields, defaults, returns, and exceptions.

## Members

- [AnalysisRunner](#api-AnalysisRunner)
- [AnalysisRunner.__init__](#api-AnalysisRunner-__init__)
- [AnalysisRunner.backend](#api-AnalysisRunner-backend)
- [AnalysisRunner.validate](#api-AnalysisRunner-validate)
- [AnalysisRunner.explain](#api-AnalysisRunner-explain)
- [AnalysisRunner.run](#api-AnalysisRunner-run)

<a id="api-AnalysisRunner"></a>
## `AnalysisRunner`

Configures execution of one analysis. backend can override the plan; run creates independent resources and returns an AnalysisResult that must be closed. A runner can normally be reused while each result is managed separately.

```python
AnalysisRunner(backend=None)
```


Source: [`src/chronaxis/runner.py:23`](../../../../src/chronaxis/runner.py#L23) (line numbers refer to `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`).

<a id="api-AnalysisRunner-__init__"></a>
### `AnalysisRunner.__init__`

Selects an optional plan-backend override without reading source or configuration files.

```python
AnalysisRunner.__init__(backend=None)
```

#### Parameters

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`backend`|str &#124; None|No|None|Positional or keyword. "reference" selects independent reference calculations; "numpy" selects NumPy array calculations. None uses the plan setting.|

#### Returns

None; initializes the instance.

#### Raises

TypeError for a non-string override; ValueError for an unknown backend.

Exact diagnostics reported directly by this function (Chinese text is retained):

- `TypeError`: `AnalysisRunner backend需要reference、numpy或None。` — backend must be reference, numpy, or None.
- `ValueError`: `AnalysisRunner仅支持reference与numpy后端。` — only reference and numpy are supported.

Source: [`src/chronaxis/runner.py:30`](../../../../src/chronaxis/runner.py#L30) (line numbers refer to `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`).

<a id="api-AnalysisRunner-backend"></a>
### `AnalysisRunner.backend`

Reads the constructor override, not the effective backend of a plan that has not yet run.

```python
AnalysisRunner.backend
```

Decorators: `property`.

Read this as a property, without calling parentheses.


#### Parameter notes

None.

#### Returns

None/reference/numpy.

#### Raises

None.

Source: [`src/chronaxis/runner.py:45`](../../../../src/chronaxis/runner.py#L45) (line numbers refer to `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`).

<a id="api-AnalysisRunner-validate"></a>
### `AnalysisRunner.validate`

Reports declaration validity and available execution paths without reading analysis data.

```python
AnalysisRunner.validate(plan)
```

#### Parameters

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`plan`|[AnalysisPlan](AnalysisPlan.md#api-AnalysisPlan)|Yes|None|Positional or keyword. An AnalysisPlan built with load_analysis_plan("analysis.yaml") or AnalysisPlan.from_dict(config). A filename string is not accepted here.|

#### Returns

The shared ValidationReport, retaining warnings about actual fields/ranges that have not been verified.

#### Raises

TypeError if plan is not AnalysisPlan or its execution model is invalid. Ordinary static problems appear in ValidationReport.errors; execution_ready reports execution capability. Inputs are not read, so an empty errors list does not verify real logs.

#### Side effects

No source I/O or directory creation.

Source: [`src/chronaxis/runner.py:65`](../../../../src/chronaxis/runner.py#L65) (line numbers refer to `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`).

<a id="api-AnalysisRunner-explain"></a>
### `AnalysisRunner.explain`

Lists dependencies, per-node backends, history requirements, and declared budgets without starting analysis.

```python
AnalysisRunner.explain(plan)
```

#### Parameters

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`plan`|[AnalysisPlan](AnalysisPlan.md#api-AnalysisPlan)|Yes|None|Positional or keyword. An AnalysisPlan built with load_analysis_plan("analysis.yaml") or AnalysisPlan.from_dict(config). A filename string is not accepted here.|

#### Returns

ExplainReport; plan_identity retains the original declaration identity.

#### Raises

TypeError for an invalid plan or execution type. Manually corrupted typed references can cause AttributeError/KeyError; rebuild a valid plan through from_dict/load_analysis_plan. This method does not open CSV/DBC or measure runtime/memory.

#### Side effects

Does not read CSV/DBC or measure actual resource use.

Source: [`src/chronaxis/runner.py:75`](../../../../src/chronaxis/runner.py#L75) (line numbers refer to `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`).

<a id="api-AnalysisRunner-run"></a>
### `AnalysisRunner.run`

Validates and performs one analysis, closing all inputs before returning an independent AnalysisResult.

```python
AnalysisRunner.run(plan, work_dir=None)
```

#### Parameters

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`plan`|[AnalysisPlan](AnalysisPlan.md#api-AnalysisPlan)|Yes|None|Positional or keyword. An AnalysisPlan built with load_analysis_plan("analysis.yaml") or AnalysisPlan.from_dict(config). A filename string is not accepted here.|
|`work_dir`|str &#124; Path &#124; None|No|None|Positional or keyword. Exclusive intermediate-work directory for this run. An explicit path must not exist; old directories are not overwritten. None creates a unique directory automatically.|

#### Returns

AnalysisResult in analysis_complete state. The caller closes it explicitly or with a context manager; write publishes separately.

#### Raises

TypeError for an invalid plan; validation/runtime failures raise AnalysisError retaining their cause and diagnostics. KeyboardInterrupt/SystemExit propagate unchanged. If cleanup remains incomplete, retry through runner_cleanup_owner.close.

#### Side effects

Creates staging for this run and scans sources once; any required subsequent history reads use the new staging. Publication is separate, and the returned result owns its cleanup lifecycle.

#### Example

```python
"""Run a YAML plan and stream results; optionally publish to a new directory."""
import argparse
from pathlib import Path

from chronaxis import AnalysisRunner, load_analysis_plan, validate_analysis_plan


def main():
    """Validate, run, and close cursors/results. Return None; preserve error chains."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', nargs='?', type=Path, default=Path(__file__).parent / 'analysis.yaml')
    parser.add_argument('--output', type=Path, help='New output directory; omit to print results only')
    args = parser.parse_args()
    plan = load_analysis_plan(args.plan)
    report = validate_analysis_plan(plan)
    if not report.valid or not report.execution_ready:
        raise RuntimeError(report)
    with AnalysisRunner().run(plan) as result:
        rows = result.iter_calculations()
        try:
            for row in rows:
                print(row.calculation_id, row.value, row.unit, row.status, row.reason)
        finally:
            rows.close()
        if args.output is not None:
            manifest = result.write(args.output)
            print(manifest)


if __name__ == '__main__':
    main()

```

Source: [`src/chronaxis/runner.py:86`](../../../../src/chronaxis/runner.py#L86) (line numbers refer to `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`).
