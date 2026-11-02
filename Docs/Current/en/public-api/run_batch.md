# chronaxis.run_batch

Import this object from `chronaxis`. This page covers directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.batch.api.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-run_batch"></a>
## `run_batch`

Run independent analyses and write a batch report. Spawn workers load, analyze, publish, and clean up each job separately. In a Python script, call this inside a main guard.

```python
run_batch(plan: BatchPlan, output_dir, *, process_count: int | None=None, cancel_event=None, device_label='pending')
```

| Parameter | Type | Required / default | Meaning |
|---|---|---|---|
| `plan` | [BatchPlan](BatchPlan.md#api-BatchPlan) | Required | Positional or keyword. BatchPlan from `load_batch_plan("batch.yaml")`, not a filename or an ordinary analysis plan. |
| `output_dir` | str &#124; Path | Required | Positional or keyword. New batch output directory with job-ID subdirectories. Existing targets cannot be overwritten. |
| `process_count` | int &#124; None | Optional; None | Keyword-only positive worker-count override; None uses BatchPlan.process_count without modifying the original plan. |
| `cancel_event` | [threading.Event](https://docs.python.org/3.12/library/threading.html#event-objects) &#124; None | Optional; None | Keyword-only optional signal. set() from another thread stops new dispatch while running jobs finish cleanup. |
| `device_label` | str | Optional; `'pending'` | Keyword-only verified device label, such as home/work, or pending when unknown. Descriptive only; not inferred from paths. |

Returns [BatchReport](BatchReport.md#api-BatchReport), retaining failed/cancelled statuses rather than reporting universal success.

Raises `TypeError` for a non-BatchPlan or invalid cancellation type and `ValueError` for invalid concurrency, backend, or job declarations. Directory, scheduling, and report-publication failures retain their specific exception types. If a report already exists, the exception's `batch_report` stores actual progress; the caller must still close it to handle cleanup_pending. Individual job failures normally remain in report.jobs rather than failing the entire function. See [errors by execution stage](../troubleshooting.md#api-errors).

```python
from chronaxis import load_batch_plan, run_batch

def main():
    # Prepare batch.yaml first; batch-output must not already exist.
    report = run_batch(load_batch_plan("batch.yaml"), "batch-output")
    try:
        print(report.to_dict())
    finally:
        report.close()

if __name__ == "__main__":
    main()
```

## Source locations

- [`src/chronaxis/batch/api.py:13`](../../../../src/chronaxis/batch/api.py#L13) — line at `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`.
