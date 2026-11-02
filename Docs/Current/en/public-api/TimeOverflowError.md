# chronaxis.TimeOverflowError

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.timebase.conversion.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-TimeOverflowError"></a>
## `TimeOverflowError`

Reject a coordinate, shifted coordinate, or nonnegative span outside int64. The exception carries no wrapped result that could be mistaken for valid data; callers record the failure as a task validation error. It adds no mutable state, opens no resources, and does not turn failure into zero duration.

```python
class TimeOverflowError(OverflowError)
```

Base class: `OverflowError`. No additional fields are declared by this class.

## Source locations

- [`src/chronaxis/timebase/conversion.py:38`](../../../../src/chronaxis/timebase/conversion.py#L38) — line at `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`.
