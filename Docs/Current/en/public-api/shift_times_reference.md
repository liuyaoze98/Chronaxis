# chronaxis.shift_times_reference

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.timebase.conversion.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-shift_times_reference"></a>
## `shift_times_reference`

Apply an offset independently to each coordinate as an integer reference for array kernels.

```python
shift_times_reference(times: Sequence[int], offset_ns: int) -> tuple[int, ...]
```

| Parameter | Type | Required / default | Meaning |
|---|---|---|---|
| `times` | Sequence[int] | Required | Positional or keyword. Coordinates already expressed in nanoseconds; sorting is not required. |
| `offset_ns` | int | Required | Positional or keyword. Valid int64 offset. |

Returns a new `tuple[int, ...]`; empty input returns an empty tuple. Raises `TypeError` or `TimeOverflowError` for invalid argument types or any out-of-range input/result.

No side effects: it does not import or call NumPy implementations or modify the input.

## Source locations

- [`src/chronaxis/timebase/conversion.py:319`](../../../../src/chronaxis/timebase/conversion.py#L319) — line at `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`.
