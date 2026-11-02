# chronaxis.parse_datetime_ns

Import this object from `chronaxis`. This page covers its directly public members and necessary construction/context protocols. See the [Chinese implementation reference](../../reference/chronaxis.timebase.conversion.md) for internals. Return to the [public API index](../api.md). Check required parameters, defaults, returns, and exceptions before calling.

<a id="api-parse_datetime_ns"></a>
## `parse_datetime_ns`

Convert a complete ISO date/time to UTC integer nanoseconds, preserving sub-microsecond fractions.

```python
parse_datetime_ns(text: str, source_timezone: tzinfo | None=None) -> TimeConversion
```

| Parameter | Type | Required / default | Meaning |
|---|---|---|---|
| `text` | str | Required | Positional or keyword. `YYYY-MM-DDTHH:MM:SS[.fraction][Z/±HH:MM]`; a space separator is also allowed. |
| `source_timezone` | tzinfo &#124; None | Optional; None | Positional or keyword. A tzinfo instance for text without an offset, such as `timezone.utc` or `timezone(timedelta(hours=8))` from datetime. YAML timezone strings are not accepted. An explicit offset in the text takes precedence. Text without an offset and a None timezone is an error. |

Returns [TimeConversion](TimeConversion.md#api-TimeConversion) containing UTC epoch nanoseconds, quantization information, and the timezone actually used, never an assumed machine default.

Raises `TypeError`/`ValueError` for invalid text/timezone, a naive datetime without a timezone, or ambiguous/nonexistent local time; `TimeOverflowError` for int64 overflow; and `OverflowError` when UTC conversion crosses datetime's calendar bounds.

No side effects: it does not consult the system timezone, load IANA timezone names, or access files.

## Source locations

- [`src/chronaxis/timebase/conversion.py:236`](../../../../src/chronaxis/timebase/conversion.py#L236) — line at `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`.
