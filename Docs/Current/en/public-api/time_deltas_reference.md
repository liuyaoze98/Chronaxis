# chronaxis.time_deltas_reference

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.timebase.conversion.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-time_deltas_reference"></a>
## `time_deltas_reference`

Calculate adjacent spans in a nondecreasing integer timeline. Separate samples may share a timestamp.

```python
time_deltas_reference(times: Sequence[int]) -> tuple[int, ...]
```

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`times`|Sequence[int]|Yes|No default|Positional or keyword. Int64 nanosecond coordinates in source order; duplicates are allowed.|

Returns `tuple[int, ...]` of nonnegative int64 spans with length `max(N-1, 0)`.

Raises `TypeError`/`ValueError` for nonintegers or time moving backward, and `TimeOverflowError` for an input or span outside int64 even when each endpoint separately fits. A decreasing sequence specifically raises `ValueError` (“时间序列必须非递减。”: the time sequence must be nondecreasing).

No side effects: the Python-integer reference calls no NumPy kernel and neither sorts nor deduplicates input.

## Source locations

- [`src/chronaxis/timebase/conversion.py:344`](../../../../src/chronaxis/timebase/conversion.py#L344) — line at `8904c2f744951857659abd40aaa3535d57faf53c`.
