# chronaxis.BatchJob

Import this object from `chronaxis`. This page covers directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.batch.models.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-BatchJob"></a>
## `BatchJob`

Declare one independent analysis. Continuous files from the same session belong in one plan within this job.

```python
BatchJob(job_id: str, plan: chronaxis.planning.plan.AnalysisPlan | pathlib.Path) -> None
```

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`job_id`|str|Yes|No default|Unique job name within the batch, such as `test_a`, used for output directories and report lookup. Names differing only in case are not allowed.|
|`plan`|[AnalysisPlan](AnalysisPlan.md#api-AnalysisPlan) &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|Yes|No default|Plan object or pathlib.Path, such as `Path("analysis.yaml")`. A bare string is not accepted by the direct constructor. Path-based plans load when the job actually starts.|

## Source locations

- [`src/chronaxis/batch/models.py:44`](../../../../src/chronaxis/batch/models.py#L44) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
