# chronaxis.ExportManifest

Import this object from `chronaxis`. Direct signal-CSV and raw-message export functions return it to identify the files produced by this operation. Return to the [public API index](../api.md); see [signal exports](../signal-exports.md) and [raw-message exports](../can-exports.md) for usage.

## Members

- [`ExportManifest`](#api-ExportManifest)

<a id="api-ExportManifest"></a>
## `ExportManifest`

```python
ExportManifest(output_dir: pathlib.Path, manifest_path: pathlib.Path, output_files: tuple[pathlib.Path, ...]) -> None
```

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`output_dir`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|Yes|No default|Directory containing this export; previous results may also be present.|
|`manifest_path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|Yes|No default|This export's timestamped completion manifest, such as `manifest_20261103_120000_000001.json`.|
|`output_files`|tuple[[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path), ...]|Yes|No default|Data files exported by this operation. The completion manifest is provided separately by manifest_path.|

Normally, read the object returned by the export function instead of constructing one. Use its paths or the manifest's `files` entries rather than fixed filenames. The constructor checks path types and parent-directory relationships; it does not prove that files exist. Invalid types raise `TypeError`; paths outside output_dir raise `ValueError`.

```python
# exported is returned by export_signal_csv(...) or export_can_frames(...).
print(exported.manifest_path)
for path in exported.output_files:
    print(path)
```

## Source locations

- [`src/chronaxis/results/manifest.py:360`](../../../../src/chronaxis/results/manifest.py#L360) — line at `8904c2f744951857659abd40aaa3535d57faf53c`.
