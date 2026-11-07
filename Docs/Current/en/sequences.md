<a id="请求响应配对"></a>
# Request/response pairing

Use request/response pairing to determine whether each request receives a response within a permitted delay, and to distinguish a confirmed timeout from insufficient observation. The result records both event times and the delay.

Fields below are relative to `sequences[]`, not the configuration root. The fragment assumes bool signals `request` and `response`, unit `1`, sharing an aligned clock. In [teaching-base.yaml](../examples/teaching-base.yaml), replace or add the root `rules` and `sequences` lists. Do not nest the parent keys inside existing list items.

First create request and response point events with `rules`, then refer to their rule names in `start` and `response`. These fields do not accept signal names or expressions.

Examples use `actual` time unless stated otherwise. With `fixed` or `dbc`, confirmation, waits, change windows and `delay_ns` use the selected period; timestamps and signal expiration still use actual record time. See [Time-basis comparison](intervals.md#timing-basis).

<a id="完整最小例与三种结果"></a>
## Complete examples and three outcomes

[sequence-minimal.yaml](../examples/sequence-minimal.yaml) supplies request/response signals and two point rules. A request at 1 s and response at 2 s, with a permitted delay of 0–2 s, produce `matched` and `delay_ns=1000000000`.

[sequence-outcomes.yaml](../examples/sequence-outcomes.yaml) extends observations to 8 s, with requests at 1, 3 and 6 s. The first matches the 2 s response. The second reaches 5 s without a response and produces `no_response`. Response data becomes missing at 7 s during the last wait, giving `indeterminate` at 8 s. The example also limits pending requests to two; reaching this limit does not discard older requests.

Both files run with `chronaxis run filename.yaml --output new-result`. The first contains only necessary settings; the second distinguishes no response from an unknown response.

<a id="配置片段"></a>
## Configuration fragment

A request occurs at 1 s and permits a response within 0–2 s. A response at 3 s succeeds with a 2 s delay. Without a response, distinguish a fully observed two-second wait from missing response data that prevents a conclusion. Root-level `sequences` makes this distinction.

```yaml
rules:                       # Point events used for pairing
  - name: request_edge       # Request rule name
    condition: request       # Existing bool signal
    rule_type: rising_edge   # False-to-true transition
  - name: response_edge      # Response rule name
    condition: response      # Existing bool signal
    rule_type: rising_edge   # False-to-true transition
sequences:                   # Pair requests with permitted responses
  - name: pair               # Unique pairing name
    start: request_edge      # Request rule, not signal name
    response: response_edge  # Response rule, not signal name
    max_delay: 2s            # Maximum permitted response delay
```

| Field | Type | Required/default | Meaning |
|---|---|---|---|
| name | String | Required | Unique name identifying this pairing in outputs, e.g. `pair`. |
| start | String | Required | Existing request point-rule name, e.g. `request_edge`; not a signal or expression. |
| response | String | Required | Existing response point-rule name, e.g. `response_edge`. Request and response clocks must align. |
| min_delay | Duration string | Default 0s | Nonnegative minimum delay from the protocol or test requirement. With `100ms`, earlier responses cannot match. Zero permits simultaneous response. |
| max_delay | Duration string | Required | Maximum delay, at least min_delay. A response exactly at `2s` matches a 2 s deadline; a later response does not. |
| max_pending | Integer | Default 65536 | Positive maximum number of pending requests. Exceeding it raises an error, rather than discarding requests or converting them to timeouts. |

The referenced rules may be `rising_edge`, `falling_edge` or `start_only` (with its repeat settings). `condition_duration`, `hysteresis`, `debounce` and `start_end` produce activities, and `window_delta` is not connected to pairing in this version; these cannot be used in start/response.

The optional per-pair `interval` selects actual, fixed or DBC timing and otherwise inherits `intervals.default`; see [Calculation intervals](intervals.md). The minimal example omits min_delay and max_pending to use 0s and 65536.

<a id="多个请求同时等待时"></a>
## Multiple pending requests

A response is assigned once, to the **earliest pending request whose permitted time range includes it** (FIFO). With requests at 1 and 2 s and a response at 3 s, both permitting 0–3 s delays, the response goes to the 1 s request and the other continues waiting.

Simultaneous request and response can match when min_delay is zero, regardless of column order in the file. A response exactly at the deadline is matched before concluding that no response occurred.

<a id="配对结果"></a>
## Pairing results

| status | Meaning | delay_ns / response |
|---|---|---|
| matched | A response falls inside the permitted range | Delay under the selected basis and the response event |
| no_response | The response condition remained observable throughout the wait but no response point occurred | None |
| indeterminate | Missing/expired response data or early end of observations prevents a conclusion | None |

For a 0–2 s permitted delay:

| Request | What happens | Outcome |
|---|---|---|
| 1 s | Response at 3 s | matched; 2 s delay |
| 4 s | Response data missing from 5 s; no match by deadline | indeterminate at 6 s |
| 7 s | Response at 9 s | matched; 2 s delay |
| 10 s | Observed through 12 s; response condition known, no response point | no_response after the full 2 s wait |

No request means no pairing row, not a fabricated zero-delay row. Within an existing `AnalysisResult` context, read rows as follows; full resource management is in [Python usage](api-usage.md).

```python
rows = result.iter_sequences()
try:
    for row in rows:
        delay_s = None if row.delay_ns is None else row.delay_ns / 1_000_000_000
        print(row.request_id, row.response_id, row.status, delay_s, row.decided_ns)
finally:
    rows.close()
```

`decided_ns` is the decision timestamp. `request_id` and `response_id` link to events; look up the request event's `confirmed_ns` for its occurrence time. A pairing row does not embed a copy of the entire event. See [SummarySequenceRow (Chinese implementation reference)](../reference/chronaxis.results.summary.md#api-SummarySequenceRow).

<a id="跨来源配对的同步要求"></a>
## Synchronizing separate sources

If a response recorder starts its clock two seconds after the request recorder, its 1 s corresponds to the request recorder's 3 s. Apply `offset="2s"` to that source and supply the synchronization basis. Giving both sources the same `time.clock` name does not establish synchronization. See the [clock examples](inputs.md). Known fixed offsets are supported; clock error or drift is not estimated automatically.

Unrelated experiments cannot be paired; run them as [independent tasks](batch.md). The `command_response` [preset](presets.md) creates the two rising-edge rules for you. Low-level implementations are documented in [sequence](../reference/chronaxis.core.sequence.md) and [sequence_reference](../reference/chronaxis.core.sequence_reference.md) (Chinese implementation references); normal usage goes through AnalysisRunner.
