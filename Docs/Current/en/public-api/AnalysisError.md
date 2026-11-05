# chronaxis.AnalysisError

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.results.errors.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-AnalysisError"></a>
## `AnalysisError`

Indicates analysis or result-publication failure. The exception itself does not promise that existing output was rolled back.

```python
class AnalysisError(RuntimeError)
```

Base class: `RuntimeError`. No additional fields are declared by this class.

## Source locations

- [`src/chronaxis/results/errors.py:8`](../../../../src/chronaxis/results/errors.py#L8) — line at `e65c920526335247bcc1ed25852bcc967f55f2fd`.
