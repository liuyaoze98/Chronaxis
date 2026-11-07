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
|`plan_path`|See purpose|Yes|No default|str or Path to a batch_version 1 jobs or template plan. Every job must satisfy the fast capability subset.|
|`output`|See purpose|Yes|No default|str or Path to a reusable batch output directory. Job outputs and batch reports use names allocated exclusively for this run.|
|`process_count`|See purpose|No|None|Positive integer or None. None uses the batch plan setting; an integer overrides its process limit. Boolean values are not valid counts.|
|`cancel_event`|See purpose|No|None|`threading.Event` or `None`. Call `set()` to stop pending dispatch and request running fast jobs to stop. After a five-second cooperative grace period, process cleanup begins. Already finished jobs may remain completed; inspect each job's status, error_type and error_message. Other objects merely providing is_set() are not accepted.|
|`total`|See purpose|No|False|Boolean. True requests totals for a same-template batch with matching definitions. Completeness is checked per calculation; missing values are not zero. No extra total is computed by default.|

### Returns

pathlib.Path to the batch report. It can contain failed or unstarted jobs; returning a path does not mean every job succeeded. Inspect the report.

### Raises

PlanValidationError for invalid plans and TypeError for an invalid total argument. Infrastructure errors propagate and may carry a saved batch_report. Job failures follow the plan fail_fast policy.

### Execution and resources

Starts worker processes, reads job inputs, writes reports, and closes batch resources internally. On Windows, call inside an `if __name__ == "__main__":` guard.

[High-performance integrator tutorial](../fast-energy.md)

Source: [`src/chronaxis/fast/batch.py:51`](../../../../src/chronaxis/fast/batch.py#L51) (line at `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`).
