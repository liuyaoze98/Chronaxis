# chronaxis.load_analysis_plan

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.planning.plan.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-load_analysis_plan"></a>
## `load_analysis_plan`

Load JSON/YAML and explicit shared definitions, apply supported overrides, and compile a plan. Input-directory declarations expand filenames. Missing signal type, unit, or enum choices can require DBC metadata, but business-message records are not scanned.

```python
load_analysis_plan(path: Path | str) -> AnalysisPlan
```

| Parameter | Type | Required / default | Meaning |
|---|---|---|---|
| `path` | [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; str | Required | Positional or keyword. Configuration file path, not a directory to scan or an arbitrary path object. Read as UTF-8, allowing an initial BOM. |

Returns a checked and compiled [AnalysisPlan](AnalysisPlan.md#api-AnalysisPlan). It loads the main configuration/shared definitions, expands declared file sets, and reads DBC metadata as needed; it does not read business-message or CSV records.

Raises `PlanValidationError` for invalid path type, file read/encoding failures, JSON/YAML syntax, duplicate keys, nonfinite constants, or invalid declarations. Load errors include configuration file location and preserve detailed causes through exception chaining.

Side effects: opens configuration/shared files, reads DBCs or enumerates directories as needed, and closes handles before normal or exceptional return. Does not create result files.

```python
from chronaxis import load_analysis_plan
plan = load_analysis_plan("Docs/Current/examples/analysis.yaml")
```

## Source locations

- [`src/chronaxis/planning/plan.py:258`](../../../../src/chronaxis/planning/plan.py#L258) — line at `66a66ec751da79d6562f341e646dd7f47c726f68`.
