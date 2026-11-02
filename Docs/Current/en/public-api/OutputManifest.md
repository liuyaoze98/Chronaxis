# chronaxis.OutputManifest

Import this object from `chronaxis`. This page lists its direct public members and necessary construction/context protocols. See the [module reference](../../reference/chronaxis.results.manifest.md) for internal implementation (Chinese implementation reference).

Return to the [public API index](../api.md). Linked parameter types lead to their definitions. Check required fields, defaults, return values, and exceptions before use.

## Members

- [OutputManifest](#api-OutputManifest)

<a id="api-OutputManifest"></a>
## `OutputManifest`

Stores the successfully published directory, manifest, and row counts for the fixed set of supported tables. Legacy output appears only when enabled.

```python
OutputManifest(run_id: str, output_dir: pathlib.Path, manifest_path: pathlib.Path, output_files: tuple[pathlib.Path, ...], row_counts: tuple[tuple[str, int], ...], status: str = 'completed') -> None
```

### Properties and data fields

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`run_id`|str|Yes|None|Unique run identity, associated with the published manifest and resource records.|
|`output_dir`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|Yes|None|Absolute Path of the successfully published result directory.|
|`manifest_path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|Yes|None|Absolute Path of the published run_manifest.json.|
|`output_files`|tuple[[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path), ...]|Yes|None|Tuple of file paths actually published in this operation.|
|`row_counts`|tuple[tuple[str, int], ...]|Yes|None|Actual row counts for each supported result table.|
|`status`|str|No|'completed'|Publication status; successful publication is completed.|

Source: [`src/chronaxis/results/manifest.py:320`](../../../../src/chronaxis/results/manifest.py#L320) (line numbers refer to `66a66ec751da79d6562f341e646dd7f47c726f68`).
