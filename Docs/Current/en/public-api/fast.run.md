# chronaxis.fast.run

`from chronaxis.fast import run`

<a id="api-run"></a>
## `run`

High-performance integrator: one session accumulates same-frame contributions from one or more ASC/BLF volumes in a deterministic order and publishes one summary.

```python
run(config: str | pathlib.Path, output: str | pathlib.Path, *, process_count: int | None = None, work_dir: str | pathlib.Path | None = None, cancel_event: object | None = None) -> pathlib.Path
```

| Name | Type | Required | Default | Purpose |
|---|---|---|---|---|
|`config`|str &#124; pathlib.Path|Yes|No default|YAML/JSON analysis path. One source lists all session volumes in paths; relative input/DBC paths resolve against the configuration. Only the fast current-message numeric subset is supported.|
|`output`|str &#124; pathlib.Path|Yes|No default|Result directory, which may exist. Timestamped output files preserve earlier results.|
|`process_count`|int &#124; None|No|None|Optional positive integer worker limit, excluding the main process. None uses execution.process_count, default 1 inline. Capped at file count; booleans are rejected and configuration is unchanged.|
|`work_dir`|str &#124; pathlib.Path &#124; None|No|None|Optional parent directory for temporary contributions. None uses system temporary storage. This invocation removes its private temporary files after completion or failure.|
|`cancel_event`|object &#124; None|No|None|Optional cancellation event with is_set(), such as threading.Event. set() requests cancellation and cleanup; run raises InterruptedError without publishing a successful summary.|

### Returns

pathlib.Path to the completion manifest. inputs lists every file and outputs names the result table. Missing values and valid zeros are determined per calculation across the session.

### Raises

PlanValidationError for configuration errors; ValueError for invalid overrides or numeric/protocol errors; RuntimeError for resource or worker failures; InterruptedError for cancellation; OSError for file/publication failures. Any required-file failure prevents a successful session result. Session errors keep their original type. If cleanup remains incomplete, the original exception may expose fast_session_cleanup_owner; resolve the resource fault and call that object's close(), without separately closing its children. The attribute is optional and may refer to an object closed by a later retry.

### Execution and resources

Read configuration, DBC and volumes. Workers evaluate individual contributions; the main process accumulates them in order. One worker runs inline; multi-file time_order requires staging. Protect multiprocessing calls with `if __name__ == "__main__":` on Windows. Publish the manifest last.

[High-performance integrator tutorial](../fast-energy.md)

Source: [`src/chronaxis/fast/run.py:65`](../../../../src/chronaxis/fast/run.py#L65) (line at `8904c2f744951857659abd40aaa3535d57faf53c`).
