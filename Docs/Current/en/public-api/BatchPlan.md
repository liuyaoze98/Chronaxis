# chronaxis.BatchPlan

Import this object from `chronaxis`. This page covers directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.batch.models.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

## Members

- [BatchPlan](#api-BatchPlan)
- [from_dict](#api-BatchPlan-from_dict)

<a id="api-BatchPlan"></a>
## `BatchPlan`

Store batch configuration for independent plans. Do not split one continuous session into separate time jobs.

```python
BatchPlan(jobs: tuple[chronaxis.batch.models.BatchJob, ...], process_count: int = 1, fail_fast: bool = False, backend: str | None = None) -> None
```

| Field | Type | Required / default | Meaning |
|---|---|---|---|
| `jobs` | tuple[[BatchJob](BatchJob.md#api-BatchJob), ...] | Required | Job tuple, such as `(BatchJob("a", Path("a.yaml")),)`, or loaded from YAML. Its order determines final report order. |
| `process_count` | int | Optional; 1 | Positive maximum analysis-worker count. Fewer jobs use fewer workers; an empty batch starts none. Excludes the scheduler and CAN reader subprocesses. |
| `fail_fast` | bool | Optional; False | False continues other independent jobs after failure. True stops new dispatch; started jobs finish through the batch executor's cancellation cleanup. |
| `backend` | str &#124; None | Optional; None | `reference` uses independent reference calculations; `numpy` uses NumPy arrays. None preserves plan settings. |

<a id="api-BatchPlan-from_dict"></a>
### `BatchPlan.from_dict`

Validate batch configuration. Jobs retain paths; templates are read and expanded into file sets.

```python
BatchPlan.from_dict(config, *, base_dir=None)
```

Class method.

| Parameter | Type | Required / default | Meaning |
|---|---|---|---|
| `config` | dict[str, object] | Required | Positional or keyword. `batch_version=1`; choose either `jobs` or `template` plus `inputs`. Each jobs entry requires plan; omitted name becomes `job_N` by position. Multiple-source templates need `source` to identify the target. Optional process_count, fail_fast, backend. See [batch tasks](../batch.md). |
| `base_dir` | str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None | Optional; None | Keyword-only directory for resolving relative paths. None means the current working directory. |

Returns a frozen BatchPlan. Raises `PlanValidationError` identifying invalid fields, duplicate names, missing template inputs, or source ambiguity. Jobs may be empty. Jobs retain plan paths; template mode reads the template, expands inputs, and reads DBC metadata if needed, but does not scan business-message records.

## Source locations

- [`src/chronaxis/batch/models.py:58`](../../../../src/chronaxis/batch/models.py#L58) — line at `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`.
- [`src/chronaxis/batch/models.py:80`](../../../../src/chronaxis/batch/models.py#L80) — line at `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`.
