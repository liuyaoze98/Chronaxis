# chronaxis.BatchJobResult

Import this object from `chronaxis`. This page covers directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.batch.models.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

## Members

- [BatchJobResult](#api-BatchJobResult)
- [to_dict](#api-BatchJobResult-to_dict)

<a id="api-BatchJobResult"></a>
## `BatchJobResult`

Store a job's final state. If cleanup fails after publication, status remains `failed` and the published path is retained.

```python
BatchJobResult(job_id: str, status: str, plan_path: str | None = None, plan_identity: str | None = None, dataset_id: str | None = None, entity_id: str | None = None, session_id: str | None = None, input_identity: str | None = None, run_id: str | None = None, output_dir: pathlib.Path | None = None, error_type: str | None = None, error_message: str | None = None, error_chain: tuple[str, ...] = (), elapsed_seconds: float = 0.0, memory_budget_bytes: int | None = None, worker_pid: int | None = None, recovery: chronaxis.batch.models.CleanupHandle | None = None) -> None
```

| Field | Type | Required / default | Meaning |
|---|---|---|---|
| `job_id` | str | Required | Original job identity. |
| `status` | str | Required | `completed`: analysis, publication, and cleanup all succeeded. `failed`: any stage failed; inspect diagnostics. `cancelled`: cancellation or fail_fast prevented further execution. Failure and cancellation are distinct. |
| `plan_path` | str &#124; None | Optional; None | Absolute original plan-file path. Normally None when an AnalysisPlan was supplied directly. |
| `plan_identity` | str &#124; None | Optional; None | Obtained plan's declaration identity, not an input-content hash. None when the file plan is not yet loaded or failed to load. |
| `dataset_id` | str &#124; None | Optional; None | Obtained plan's `dataset.name`; None if not loaded or loading failed. The result property remains named `dataset_id`. |
| `entity_id` | str &#124; None | Optional; None | Optional `dataset.entity`, falling back to `dataset.name`; None if no plan was obtained. |
| `session_id` | str &#124; None | Optional; None | Optional `dataset.session`, falling back to `dataset.name`; None if no plan was obtained. |
| `input_identity` | str &#124; None | Optional; None | Input-summary identity returned by AnalysisRunner. None if no result was returned or no summary was requested; successful runs may also have None. |
| `run_id` | str &#124; None | Optional; None | Run ID when AnalysisRunner returned a result. None if failure/cancellation occurred before that. |
| `output_dir` | [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None | Optional; None | Formal directory after successful publication. Retained if subsequent cleanup fails, while status is failed. |
| `error_type` | str &#124; None | Optional; None | Exception class or `not_started` cancellation marker. None on completion; read with status and error_chain. |
| `error_message` | str &#124; None | Optional; None | Specific failure/cancellation explanation; None on completion. Causes and cleanup notes are in error_chain. |
| `error_chain` | tuple[str, ...] | Optional; () | Cause chain and cleanup notes, retaining error origin. |
| `elapsed_seconds` | float | Optional; 0.0 | Job wall-clock seconds, including publication and cleanup, not CPU time. |
| `memory_budget_bytes` | int &#124; None | Optional; None | Obtained plan's new-analysis-layer budget in bytes. None when no plan was loaded, not zero bytes. |
| `worker_pid` | int &#124; None | Optional; None | PID of the analysis worker that actually executed the job. None for unstarted jobs. Jobs reusing a process may share a PID. |
| `recovery` | [CleanupHandle](../../reference/chronaxis.batch.models.md#api-CleanupHandle) &#124; None | Optional; None | Handle retained after failed cleanup; call close() to retry. None after normal cleanup. Excluded from JSON. Type link is a Chinese implementation reference. |

<a id="api-BatchJobResult-to_dict"></a>
### `BatchJobResult.to_dict`

Convert job status, output directory, and errors to a report dictionary.

```python
BatchJobResult.to_dict() -> dict
```

No explicit parameters. Returns a JSON-compatible dict. No documented exceptions; resource objects are not serialized.

## Source locations

- [`src/chronaxis/batch/models.py:119`](../../../../src/chronaxis/batch/models.py#L119) — line at `66a66ec751da79d6562f341e646dd7f47c726f68`.
- [`src/chronaxis/batch/models.py:147`](../../../../src/chronaxis/batch/models.py#L147) — line at `66a66ec751da79d6562f341e646dd7f47c726f68`.
