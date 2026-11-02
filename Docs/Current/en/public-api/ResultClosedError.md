# chronaxis.ResultClosedError

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.results.errors.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-ResultClosedError"></a>
## `ResultClosedError`

Indicates a closed result: new iterators cannot be created and the result cannot be read or published.

```python
class ResultClosedError(AnalysisError)
```

Base class: [AnalysisError](AnalysisError.md#api-AnalysisError). No additional fields are declared by this class.

## Source locations

- [`src/chronaxis/results/errors.py:16`](../../../../src/chronaxis/results/errors.py#L16) — line at `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`.
