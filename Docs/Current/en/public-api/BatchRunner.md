# chronaxis.BatchRunner

Import this object from `chronaxis`. This page covers directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.batch.runner.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

## Members

- [`BatchRunner`](#api-BatchRunner)
- [`__init__`](#api-BatchRunner-__init__)
- [`run`](#api-BatchRunner-run)

<a id="api-BatchRunner"></a>
## `BatchRunner`

Execute independent jobs with a bounded pool of spawn workers. Continuous files within each job retain their original order.

```python
BatchRunner(process_count=1, *, fail_fast=False, backend=None)
```

<a id="api-BatchRunner-__init__"></a>
### `BatchRunner.__init__`

Configure scheduling without starting workers or reading business data.

```python
BatchRunner.__init__(process_count=1, *, fail_fast=False, backend=None)
```

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`process_count`|int|No|1|Positional or keyword. Positive maximum analysis-worker count. Fewer jobs need fewer workers; empty batches start none. Excludes scheduler and CAN reader subprocesses.|
|`fail_fast`|bool|No|False|Keyword-only. False continues later jobs after failure; True stops new dispatch after observing failure and waits for started jobs to finish cleanup.|
|`backend`|str &#124; None|No|None|Keyword-only. `reference` or `numpy`; None uses each plan's setting.|

The initializer returns None; calling BatchRunner(...) creates the instance. Invalid types, ranges, or backends are rejected. Specific errors include `ValueError` (“process_count需要正原生int。”: requires a positive native int) and `TypeError` (“fail_fast需要bool。”: requires bool).

<a id="api-BatchRunner-run"></a>
### `BatchRunner.run`

Run independent jobs and return a report in declaration order.

```python
BatchRunner.run(jobs, output_dir, *, cancel_event=None, device_label='pending') -> BatchReport
```

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`jobs`|tuple|Yes|No default|Positional or keyword. BatchJob tuple, for example `load_batch_plan("batch.yaml").jobs`; each includes an independent identity and plan.|
|`output_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|Yes|No default|Positional or keyword. Reusable batch directory. Job subdirectories use the batch timestamp; existing results are preserved.|
|`cancel_event`|[threading.Event](https://docs.python.org/3.12/library/threading.html#event-objects) &#124; None|No|None|Keyword-only. Another thread can call set() to stop new dispatch; running jobs continue to finish cleanup. None disables this cancellation signal.|
|`device_label`|str|No|'pending'|Keyword-only. Verified source-device label, such as home/work, or pending when unknown. It does not affect calculations or infer the device from paths.|

Returns [BatchReport](BatchReport.md#api-BatchReport); its close() retries failed cleanup in child processes. Declaration/path errors are rejected before creating workers. Worker-scheduler or other infrastructure errors propagate after cleanup.

Specific errors: `TypeError` if jobs is not a BatchJob tuple (“批量任务需要BatchJob tuple。”); `ValueError` for duplicate or case-colliding IDs (“批量job_id不能重复，大小写冲突也拒绝。”); `TypeError` for a non-threading.Event cancellation signal (“cancel_event需要threading.Event。”); `ValueError` for an empty/nontext device label (“device_label需要非空文本。”).

Side effects: starts at most process_count workers and publishes each job independently. Cancellation prevents dispatch only for jobs not yet dispatched.

## Source locations

- [`src/chronaxis/batch/runner.py:108`](../../../../src/chronaxis/batch/runner.py#L108) — line at `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`.
- [`src/chronaxis/batch/runner.py:111`](../../../../src/chronaxis/batch/runner.py#L111) — line at `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`.
- [`src/chronaxis/batch/runner.py:124`](../../../../src/chronaxis/batch/runner.py#L124) — line at `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`.
