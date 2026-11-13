# chronaxis.fast.batch.run_batch

`from chronaxis.fast.batch import run_batch`

<a id="api-run_batch"></a>
## `run_batch`

Run independent high-performance integration jobs in parallel. Do not use this to split paths that belong to one continuous source.

```python
run_batch(plan_path, output, *, process_count=None, cancel_event=None, total=False)
```

| Name | Type | Required | Default | Purpose |
|---|---|---|---|---|
|`plan_path`|str &#124; pathlib.Path|Yes|No default|str or Path to a batch_version 1 jobs or template plan. Every job must satisfy the fast capability subset.|
|`output`|str &#124; pathlib.Path|Yes|No default|str or Path to a reusable batch output directory. Job outputs and batch reports use names allocated exclusively for this run.|
|`process_count`|int &#124; None|No|None|Positive integer or None. None uses the batch plan setting; an integer overrides its process limit. Boolean values are not valid counts.|
|`cancel_event`|threading.Event &#124; None|No|None|`threading.Event` or `None`. Call `set()` to stop pending dispatch and request running fast jobs to stop. After a five-second cooperative grace period, process cleanup begins. Already finished jobs may remain completed; inspect each job's status, error_type and error_message. Other objects merely providing is_set() are not accepted.|
|`total`|bool|No|False|Boolean. True requests totals for a same-template batch with matching definitions. Completeness is checked per calculation; missing values are not zero. No extra total is computed by default.|

### Returns

pathlib.Path to the batch report. It can contain failed or unstarted jobs; returning a path does not mean every job succeeded. Inspect the report.

### Raises

Parameter and combination errors raise directly instead of returning a normal batch report: TypeError for a non-bool total; ValueError for process_count that is not a positive native int, including bool; TypeError for cancel_event other than threading.Event or None; ValueError for total=True with jobs. Totals require independent files expanded from one template with matching calculation definitions. The total type is checked before loading configuration; the other overrides and combinations are checked after configuration preparation and before dispatch.

Configuration parsing or fast-capability failures raise PlanValidationError. Ordinary failures in dispatched jobs appear in report.jobs with status, error_type, and error_message; fail_fast controls further dispatch. Returning a report path does not mean every job succeeded.

Communication, scheduling, cleanup, and report-publication errors propagate. An exception may carry a saved batch_report, but pre-dispatch and publication failures do not guarantee that attribute. If worker construction is interrupted and cleanup remains incomplete, the original exception may also expose batch_worker_cleanup_owner. That unfinished worker may not belong to a report job; close an available recovery object separately.

### Execution and resources

Starts worker processes, reads job inputs, writes reports, and closes batch resources internally. On Windows, call inside an `if __name__ == "__main__":` guard.

[High-performance integrator tutorial](../fast-energy.md)

Source: [`src/chronaxis/fast/batch.py:51`](../../../../src/chronaxis/fast/batch.py#L51) (line at `8904c2f744951857659abd40aaa3535d57faf53c`).
