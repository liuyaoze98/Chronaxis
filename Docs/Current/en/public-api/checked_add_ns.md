# chronaxis.checked_add_ns

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.timebase.conversion.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-checked_add_ns"></a>
## `checked_add_ns`

Add a fixed offset to a nanosecond coordinate, checking the int64 range.

```python
checked_add_ns(time_ns: int, offset_ns: int) -> int
```

| Parameter | Type | Required / default | Meaning |
|---|---|---|---|
| `time_ns` | int | Required | Positional or keyword. Original int64 coordinate in nanoseconds. |
| `offset_ns` | int | Required | Positional or keyword. Int64 offset in nanoseconds. |

Returns the exact new integer coordinate. Successful addition does not establish synchronization between sources.

Raises `TypeError` if either argument is not a non-boolean integer. Raises `TimeOverflowError` if either argument or the sum is outside int64.

## Source locations

- [`src/chronaxis/timebase/conversion.py:301`](../../../../src/chronaxis/timebase/conversion.py#L301) — line at `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`.
