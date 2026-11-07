<a id="数据集与分析范围"></a>
# Dataset and analysis range

For ordinary analysis, name the inputs with `dataset.name`. `entity`, `session` and a time range can be omitted: the two identifiers inherit `name`, and the range comes from actual observations. Files are declared in `sources`, not selected by the dataset name. One analysis describes one entity in one common session; use [batch tasks](batch.md) for independent tests. These identifiers appear in results.

<a id="配置位置与示例"></a>
## Configuration location and example

This root-level mapping sits alongside `sources` and `signals`. Start with [analysis.yaml](../examples/analysis.yaml) and replace its existing `dataset:` section; do not add a second `dataset`, or put a list marker before it.

```yaml
dataset:              # Name this analysis; other dataset fields are optional
  name: bench_run_01  # Identifies the dataset in results
```

Set `entity` and `session` only when equipment and acquisition runs need separate labels. They do not select files or prove that sources are synchronized. Add `domain` only to restrict the time range. The reference table describes choices for those needs, not a checklist of required fields.

<a id="只分析2到5秒"></a>
## Analyze only 2 to 5 seconds

Replace the `dataset` section of [analysis.yaml](../examples/analysis.yaml):

```yaml
dataset:        # Name the analysis and restrict its requested time range
  name: energy  # Dataset name included in results
  domain:       # Use the same time basis as the sources
    start: 2s   # Include this starting instant
    end: 5s     # Exclude this endpoint from continuous duration
```

The reference calls these positions `dataset.domain.start` and `dataset.domain.end`: find `dataset`, then `domain`, then `start` or `end`. The actual keys do not contain dots. `domain: {start: 2s, end: 5s}` is the equivalent inline mapping. See [configuration syntax](configuration-language.md#field-paths).

The synthetic ASC records power 2, 4, 8 and 10 W at 0, 1, 3 and 4 s, with an unrelated message at 6 s establishing observation through that time. Selecting 2–5 s gives 4 W during 2–3 s, 8 W during 3–4 s and 10 W during 4–5 s: **4×1 + 8×1 + 10×1 = 22 J**. The real samples within the range are 8 W at 3 s and 10 W at 4 s, giving sample mean 9 W and time mean 22/3 W. The held value at 2 s contributes to integration but is not an additional sample. These numbers apply to the supplied synthetic ASC.

<a id="字段参考"></a>
## Field reference

| Full path | Type, required status and default | Purpose and constraints |
|---|---|---|
| `dataset.name` | Required string | Name these inputs/results, for example `run_01` and `run_02`. The program retains your choice rather than deriving it from filenames. Identifier syntax is below. |
| `dataset.entity` | Optional string; defaults to name | Equipment or specimen label, such as `motor_01`, taken from project records. It does not select a DBC or convert units. |
| `dataset.session` | Optional string; defaults to name | Label the common acquisition session, such as `warmup`. Joint analysis has one session but still needs source clock alignment. |
| `dataset.domain` | Optional mapping | Requested range containing both `start` and `end`. Omission uses actual observations. Neither `null` nor `{}` means the whole file. |
| `dataset.domain.start` | Required time string when domain is supplied | Inclusive start, in calibrated source time: for example `0s` or `2026-01-01T08:00:00+08:00`. Apply source offsets before comparing clocks. |
| `dataset.domain.end` | Required time string when domain is supplied | End not earlier than start, excluded from continuous calculation. 0–6 s means six seconds; equal endpoints mean zero duration. Real samples at the endpoint may inform boundary decisions but do not extend duration. |
| `dataset.metadata` | Optional mapping; defaults to `{}` | Project-defined notes, such as `{operator: tester_01}`. Omission records no notes and changes no input, time or calculation. |

The first three identifiers start with an English letter or underscore, followed by letters, digits or underscores. Python keywords and reserved expression names such as `abs` and `isclose` are disallowed. Empty strings, nulls and numbers are not identifiers.

`0s` is a time string with a unit, `0` is a number, and `null` is an empty value. CSV time columns may use bare numbers interpreted by `sources[].time.unit`; analysis endpoints require an explicit time representation. Source `time.offset` is applied before comparing input time to the requested range.

<a id="请求范围与实际观测范围"></a>
## Requested versus observed range

A request for `[0,12)` with observations ending at 8 s does not make 8–12 s valid. The program retains the requested range and missing-data information; `valid_for` cannot extend observation. [Execution](execution.md) and [calculation](calculations.md) settings determine whether partial data is accepted.

<a id="省略分析范围"></a>
## Omit the analysis range

Both ordinary analysis and per-message accumulation allow `domain` to be omitted. The program obtains first/last observation times during the same read, without a preliminary file scan or storing complete history just to determine the range. Rules, sequences, windows, calculations and requested exports use it.

If source A ends at 8 s and B at 5 s, the session extends to 8 s while B's missing data is handled separately. Empty inputs produce no events and null session statistics with `no_observation`; an always-true rule does not invent an event. A single record with no later observation has equal start/end times: no sample lies inside the half-open range and no duration can accumulate. The range is not extended to the signal's expiry time.

Supply `domain` when analyzing a subset; `null` and an empty object are not omission. Source time declarations and actual synchronization evidence still determine clock alignment.
