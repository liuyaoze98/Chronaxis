# chronaxis.fast.run

`from chronaxis.fast import run`

<a id="api-run"></a>
## `run`

High-performance integrator: read one ASC or BLF file, accumulate same-frame formulas per message, and publish results on success. This is not integration over actual inter-frame time.

```python
run(config, output)
```

| Name | Type | Required | Default | Purpose |
|---|---|---|---|---|
|`config`|See purpose|Yes|No default|str or Path to a single-file YAML/JSON configuration in the fast subset. DBC and input paths are relative to the declaring configuration file.|
|`output`|See purpose|Yes|No default|str or Path to the result directory, which may already exist. This run uses timestamped filenames and does not overwrite existing results.|

### Returns

pathlib.Path to this run manifest. Read outputs for actual filenames. A file with no target frames has a null result and a reason, not a fabricated zero.

### Raises

PlanValidationError for invalid configuration; read, decode, and formula errors propagate and prevent a normal result for the file. Output I/O failures propagate OSError. This single-file API has no cancel_event parameter.

### Execution and resources

Reads configuration, DBC, and input; writes result files and publishes the completion manifest last. See the high-performance integrator tutorial for supported capabilities and complete configurations.

[High-performance integrator tutorial](../fast-energy.md)

Source: [`src/chronaxis/fast/run.py:54`](../../../../src/chronaxis/fast/run.py#L54) (line at `e65c920526335247bcc1ed25852bcc967f55f2fd`).
