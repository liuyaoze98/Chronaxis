# chronaxis.AnalysisRunner

Import this object from `chronaxis`. This page lists direct public members and necessary construction/context protocols. See the [module reference](../../reference/chronaxis.runner.md) for internal implementation (Chinese implementation reference).

Return to the [public API index](../api.md). Linked parameter types lead to their definitions. Check required fields, defaults, returns, and exceptions.

## Members

- [`AnalysisRunner`](#api-AnalysisRunner)
- [`AnalysisRunner.__init__`](#api-AnalysisRunner-__init__)
- [`AnalysisRunner.backend`](#api-AnalysisRunner-backend)
- [`AnalysisRunner.validate`](#api-AnalysisRunner-validate)
- [`AnalysisRunner.explain`](#api-AnalysisRunner-explain)
- [`AnalysisRunner.run`](#api-AnalysisRunner-run)

<a id="api-AnalysisRunner"></a>
## `AnalysisRunner`

Configures execution of one analysis. backend can override the plan; run creates independent resources and returns an AnalysisResult that must be closed. A runner can normally be reused while each result is managed separately.

```python
AnalysisRunner(backend=None, *, extensions=None)
```

<a id="api-AnalysisRunner-__init__"></a>
### `AnalysisRunner.__init__`

Selects an optional plan-backend override without reading source or configuration files.

```python
AnalysisRunner.__init__(backend=None, *, extensions=None)
```

#### Parameters

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`backend`|str &#124; None|No|None|Positional or keyword. "auto" selects reference or numpy from each whole plan without trial runs; "reference" and "numpy" fix the numerical implementation. None inherits the plan. See [execution settings](../execution.md).|
|`extensions`|[ExtensionRegistry](ExtensionRegistry.md#api-ExtensionRegistry) &#124; None|No|None|Keyword-only host registry. Supply the same instance used for the plan. Each requested extension must implement the selected backend.|

#### Returns

None; initializes the instance.

#### Raises

`TypeError` for a non-string, non-None backend or for extensions other than ExtensionRegistry or None. `ValueError` for an unknown backend string. The constructor has no plan yet; validate, explain, and run check registry identity when they receive a plan.

Exact diagnostics reported directly by this function (Chinese text is retained):

- `TypeError`: `AnalysisRunner backend需要auto、reference、numpy或None` — backend must be auto, reference, numpy, or None.
- `ValueError`: `AnalysisRunner仅支持auto、reference与numpy后端` — backend must be auto, reference, or numpy.
- `TypeError`: `extensions需要宿主建立的ExtensionRegistry` — extensions must be an ExtensionRegistry instance or None.

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

None/auto/reference/numpy.

#### Raises

None.

<a id="api-AnalysisRunner-validate"></a>
### `AnalysisRunner.validate`

Reports declaration validity and available execution paths without reading analysis data.

```python
AnalysisRunner.validate(plan, *, process_count=None)
```

#### Parameters

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`plan`|[AnalysisPlan](AnalysisPlan.md#api-AnalysisPlan)|Yes|No default|Positional or keyword. An AnalysisPlan built with load_analysis_plan("analysis.yaml") or AnalysisPlan.from_dict(config). A filename string is not accepted here.|
|`process_count`|int &#124; None|No|None|Keyword-only worker-limit override for this static check. None uses execution.process_count; a positive integer overrides without modifying the plan. No workers are started.|

#### Returns

The shared ValidationReport, retaining warnings about actual fields/ranges that have not been verified.

#### Raises

`ValueError` if an explicit `process_count` is not a positive native integer (including bool), or the runner and plan do not share the same ExtensionRegistry instance. Equal declarations in a different registry object are insufficient. These errors are raised before a report is returned. This method has no extensions argument; pass the plan's registry when constructing the runner. Unsupported execution configurations appear in static validation reports; `run` rejects them with `AnalysisError`.

TypeError if plan is not AnalysisPlan or its execution model is invalid. Ordinary static problems appear in ValidationReport.errors; execution_ready reports execution capability. Inputs are not read, so an empty errors list does not verify real logs.

#### Side effects

No source I/O or directory creation.

#### Example: share one registry instance

This minimal example checks and explains the bundled plan without running an analysis. It uses built-in operations; the empty registry demonstrates how to pass the same object. For actual custom operations, use the [worked host example](../host-extensions.md).

```python
"""Share one registry instance for loading, validation, and explanation."""
# Run from the manual root (the directory containing examples).
# This built-in teaching plan uses an empty registry only to show object sharing.
from chronaxis import AnalysisRunner, load_analysis_plan
from chronaxis.extensions import ExtensionRegistry

registry = ExtensionRegistry()
plan = load_analysis_plan("examples/calculation-minimal.yaml", extensions=registry)
runner = AnalysisRunner(extensions=registry)
validation = runner.validate(plan)
explanation = runner.explain(plan)
print(validation.valid, validation.execution_ready)
print(type(explanation).__name__)
# Expected output: True True, followed by ExplainReport.
```

<a id="api-AnalysisRunner-explain"></a>
### `AnalysisRunner.explain`

Lists dependencies, per-node backends, history requirements, and declared budgets without starting analysis.

```python
AnalysisRunner.explain(plan, *, process_count=None)
```

#### Parameters

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`plan`|[AnalysisPlan](AnalysisPlan.md#api-AnalysisPlan)|Yes|No default|Positional or keyword. An AnalysisPlan built with load_analysis_plan("analysis.yaml") or AnalysisPlan.from_dict(config). A filename string is not accepted here.|
|`process_count`|int &#124; None|No|None|Keyword-only worker-limit override for this explanation. None uses execution.process_count; a positive integer overrides without modifying the plan. Reported limits are not measured worker counts.|

#### Returns

ExplainReport; plan_identity retains the original declaration identity.

#### Raises

`ValueError` if an explicit `process_count` is not a positive native integer (including bool), or the runner and plan do not share the same ExtensionRegistry instance. Equal declarations in a different registry object are insufficient. These errors are raised before a report is returned. This method has no extensions argument; pass the plan's registry when constructing the runner. Unsupported execution configurations appear in static validation reports; `run` rejects them with `AnalysisError`.

TypeError for an invalid plan or execution type. Manually corrupted typed references can cause AttributeError/KeyError; rebuild a valid plan through from_dict/load_analysis_plan. This method does not open CSV/DBC or measure runtime/memory.

#### Side effects

Does not read CSV/DBC or measure actual resource use.

<a id="api-AnalysisRunner-run"></a>
### `AnalysisRunner.run`

Validates and performs one analysis, closing all inputs before returning an independent AnalysisResult.

```python
AnalysisRunner.run(plan, work_dir=None, *, process_count=None)
```

#### Parameters

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`plan`|[AnalysisPlan](AnalysisPlan.md#api-AnalysisPlan)|Yes|No default|Positional or keyword. An AnalysisPlan built with load_analysis_plan("analysis.yaml") or AnalysisPlan.from_dict(config). A filename string is not accepted here.|
|`work_dir`|str &#124; Path &#124; None|No|None|Positional or keyword. Exclusive intermediate-work directory for this run. An explicit path must not exist; old directories are not overwritten. None creates a unique directory automatically.|
|`process_count`|int &#124; None|No|None|Positive reading/decoding worker limit excluding the main process. None uses execution.process_count. Overrides this invocation without changing the original plan; rejects Boolean values and nonpositive counts. See continuous-file multiprocessing.|

#### Returns

AnalysisResult in analysis_complete state. The caller closes it explicitly or with a context manager; write publishes separately.

#### Raises

`TypeError` if `plan` is not an AnalysisPlan or its execution declaration has the wrong type. `ValueError` if an explicit `process_count` is not a positive native integer (including Boolean values), or the runner and plan do not share the same extension registry.

`AnalysisError` if validation fails, the plan cannot execute, or analysis fails at runtime. A newly wrapped runtime failure keeps its original error in `__cause__`; an existing AnalysisError or a direct validation error may have no cause. Additional cleanup information is available in `__notes__`, when present. PlanValidationError raised during configuration loading has a separate `diagnostics` attribute; not every AnalysisError has that attribute.

`KeyboardInterrupt` and `SystemExit` propagate unchanged. When cleanup remains incomplete, obtain `getattr(exc, "runner_cleanup_owner", None)` from the caught exception. If a recovery object is present, resolve the resource fault and retry its `close()` method. Absence of this attribute does not mean analysis succeeded; the original exception still needs handling.

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
    parser.add_argument('--output', type=Path, help='Reusable result directory; omit to print results only')
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

## Host-registered operations

Register trusted callbacks in Python and pass the same immutable registry when loading and running a v4 plan. See the [worked host example](../host-extensions.md).

## Source locations

- [`src/chronaxis/runner.py:23`](../../../../src/chronaxis/runner.py#L23) — line at `8904c2f744951857659abd40aaa3535d57faf53c`.
- [`src/chronaxis/runner.py:30`](../../../../src/chronaxis/runner.py#L30) — line at `8904c2f744951857659abd40aaa3535d57faf53c`.
- [`src/chronaxis/runner.py:52`](../../../../src/chronaxis/runner.py#L52) — line at `8904c2f744951857659abd40aaa3535d57faf53c`.
- [`src/chronaxis/runner.py:80`](../../../../src/chronaxis/runner.py#L80) — line at `8904c2f744951857659abd40aaa3535d57faf53c`.
- [`src/chronaxis/runner.py:91`](../../../../src/chronaxis/runner.py#L91) — line at `8904c2f744951857659abd40aaa3535d57faf53c`.
- [`src/chronaxis/runner.py:103`](../../../../src/chronaxis/runner.py#L103) — line at `8904c2f744951857659abd40aaa3535d57faf53c`.
