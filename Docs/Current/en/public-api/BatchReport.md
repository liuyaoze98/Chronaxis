# chronaxis.BatchReport

Import this object from `chronaxis`. This page covers directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.batch.models.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

## Members

- [BatchReport](#api-BatchReport)
- [status](#api-BatchReport-status)
- [to_dict](#api-BatchReport-to_dict)
- [close](#api-BatchReport-close)

<a id="api-BatchReport"></a>
## `BatchReport`

Summarize results in original job order. Each job's numerical tables remain in its own directory; this report does not combine values across different analysis definitions.

```python
BatchReport(output_dir: pathlib.Path, jobs: tuple[chronaxis.batch.models.BatchJobResult, ...], process_count: int, fail_fast: bool, cancel_requested: bool, device_label: str, worker_process_count: int = 0, infrastructure_error: str | None = None) -> None
```

| Field | Type | Required / default | Meaning |
|---|---|---|---|
| `output_dir` | [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) | Required | New batch directory; existing targets are not overwritten. |
| `jobs` | tuple[[BatchJobResult](BatchJobResult.md#api-BatchJobResult), ...] | Required | Final results in declaration order regardless of worker completion order. |
| `process_count` | int | Required | Configured positive maximum analysis-worker count. Scheduling defaults to 1; direct construction here requires a value. Excludes scheduler and CAN reader subprocesses. Fewer/zero jobs need fewer/zero workers. |
| `fail_fast` | bool | Required | Whether dispatch stops after observing a failure. |
| `cancel_requested` | bool | Required | Whether user cancellation or KeyboardInterrupt was observed. |
| `device_label` | str | Required | Nonempty batch-report source-device label. Only run_batch/BatchRunner.run default this to pending. Does not override child metadata.device_label. |
| `worker_process_count` | int | Optional; 0 | Actual number of analysis workers started, possibly less than process_count. Zero for an empty or pre-cancelled batch. Excludes CAN reader subprocesses. |
| `infrastructure_error` | str &#124; None | Optional; None | Scheduler/report-infrastructure error. None means no such error was recorded, not that all jobs succeeded. Inspect each job's status and diagnostics. |

<a id="api-BatchReport-status"></a>
### `BatchReport.status`

```python
BatchReport.status: str
```

Property: read without parentheses. No parameters. Returns `failed`, `cancelled`, or `completed`, with failure taking precedence. No documented exceptions.

<a id="api-BatchReport-to_dict"></a>
### `BatchReport.to_dict`

```python
BatchReport.to_dict() -> dict
```

No explicit parameters. Returns a JSON-compatible dict containing identities and counts. Does not aggregate calculation values. No documented exceptions.

<a id="api-BatchReport-close"></a>
### `BatchReport.close`

Retry all unfinished cleanup.

```python
BatchReport.close() -> None
```

No explicit parameters. Returns None, not additional calculation values. Raises the first close error after still attempting the other cleanup items.

## Source locations

- [`src/chronaxis/batch/models.py:160`](../../../../src/chronaxis/batch/models.py#L160) — line at `66a66ec751da79d6562f341e646dd7f47c726f68`.
- [`src/chronaxis/batch/models.py:173`](../../../../src/chronaxis/batch/models.py#L173) — line at `66a66ec751da79d6562f341e646dd7f47c726f68`.
- [`src/chronaxis/batch/models.py:179`](../../../../src/chronaxis/batch/models.py#L179) — line at `66a66ec751da79d6562f341e646dd7f47c726f68`.
- [`src/chronaxis/batch/models.py:190`](../../../../src/chronaxis/batch/models.py#L190) — line at `66a66ec751da79d6562f341e646dd7f47c726f68`.
