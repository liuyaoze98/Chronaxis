# chronaxis.load_batch_plan

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.batch.config.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-load_batch_plan"></a>
## `load_batch_plan`

Read a batch YAML/JSON file and construct its independent tasks and scheduling settings.

```python
load_batch_plan(path: str | Path) -> BatchPlan
```

| Parameter | Type | Required / default | Meaning |
|---|---|---|---|
| `path` | str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) | Required | Positional or keyword. Batch JSON/YAML path. Child plans, templates, and input paths are relative to this file. `jobs` plans load when each task starts; `template` expands and compiles independent plans during this call. |

Returns an immutable [BatchPlan](BatchPlan.md#api-BatchPlan) with checked batch structure. Templates are expanded, while jobs retain paths. Neither reads business-input records at this stage.

Raises `PlanValidationError` for path, syntax, batch-field, or template-expansion failures. Child-plan errors in jobs are recorded when a task starts; template compilation errors are reported before this call returns.

Side effects: reads the batch file; template mode also reads the template and necessary DBCs and enumerates inputs. Creates no output directories.

```python
from chronaxis import load_batch_plan
# Prepare batch.yaml and its child plans as described in the batch guide.
plan = load_batch_plan("batch.yaml")
```

## Source locations

- [`src/chronaxis/batch/config.py:14`](../../../../src/chronaxis/batch/config.py#L14) — line at `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`.
