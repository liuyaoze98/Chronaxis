# chronaxis.run_batch

Import this object from `chronaxis`. This page covers directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.batch.api.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-run_batch"></a>
## `run_batch`

Run independent analyses and write a batch report. Spawn workers load, analyze, publish, and clean up each job separately. In a Python script, call this inside a main guard.

```python
run_batch(plan: BatchPlan, output_dir, *, process_count: int | None=None, cancel_event=None, device_label='pending')
```

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`plan`|[BatchPlan](BatchPlan.md#api-BatchPlan)|Yes|No default|Positional or keyword. BatchPlan from `load_batch_plan("batch.yaml")`, not a filename or an ordinary analysis plan.|
|`output_dir`|str &#124; Path|Yes|No default|Positional or keyword. Reusable batch output directory with timestamped job subdirectories. Existing results are preserved.|
|`process_count`|int &#124; None|No|None|Keyword-only positive worker-count override; None uses BatchPlan.process_count without modifying the original plan.|
|`cancel_event`|[threading.Event](https://docs.python.org/3.12/library/threading.html#event-objects) &#124; None|No|None|Keyword-only optional signal. set() from another thread stops new dispatch while running jobs finish cleanup.|
|`device_label`|str|No|'pending'|Keyword-only verified device label, such as home/work, or pending when unknown. Descriptive only; not inferred from paths.|

Returns [BatchReport](BatchReport.md#api-BatchReport). Its report_path is the actual report for this batch; each job's manifest_path identifies its completion manifest. Failed/cancelled statuses remain in the report.

Raises `TypeError` for a non-BatchPlan or invalid cancellation type and `ValueError` for invalid concurrency, backend, or job declarations. Directory, scheduling, and report-publication failures retain their specific exception types. If a report already exists, the exception's `batch_report` stores actual progress; the caller must still close it to handle cleanup_pending. Individual job failures normally remain in report.jobs rather than failing the entire function. See [errors by execution stage](../troubleshooting.md#api-errors).

```python
from chronaxis import load_batch_plan, run_batch

def main():
    # Prepare batch.yaml first; batch-output may contain previous results.
    report = run_batch(load_batch_plan("batch.yaml"), "batch-output")
    try:
        print(report.report_path)
    finally:
        report.close()

if __name__ == "__main__":
    main()
```

If worker construction is interrupted and cleanup remains incomplete, the original `KeyboardInterrupt` can carry both `batch_report` and `batch_worker_cleanup_owner`. The unfinished worker may not appear in report jobs; retain it and retry its `close()` as well as report cleanup. A normal cancelled report is still returned when Ctrl+C cleanup completed.

## Source locations

- [`src/chronaxis/batch/api.py:13`](../../../../src/chronaxis/batch/api.py#L13) — line at `8904c2f744951857659abd40aaa3535d57faf53c`.
