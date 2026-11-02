# chronaxis.RunMetadata

Import this object from `chronaxis`. This page lists its direct public members and necessary construction/context protocols. See the [module reference](../../reference/chronaxis.results.manifest.md) for internal implementation (Chinese implementation reference).

Return to the [public API index](../api.md). Linked parameter types lead to their definitions. Check required fields, defaults, return values, and exceptions before use.

## Members

- [RunMetadata](#api-RunMetadata)
- [RunMetadata.estimated_bytes](#api-RunMetadata-estimated_bytes)
- [RunMetadata.to_dict](#api-RunMetadata-to_dict)

<a id="api-RunMetadata"></a>
## `RunMetadata`

Stores run identity, actual backend, time interpretation, and diagnostic summaries. Normally read it from an open AnalysisResult.metadata rather than constructing it yourself. Detailed source models are optional and have content only when a caller supplies actual reading details. The public AnalysisRunner currently leaves can_sources and text_can_sources empty; this neither means no CAN files were read nor proves a DBC was validated. See to_dict below for summary and detailed serialization.

```python
RunMetadata(run_id: str, input_identity: str | None, plan_hash: str, backend: str, config_version: int, source_time_interpretation: str, session_boundaries: tuple[tuple[str, int, int], ...], started_at: str, mapping_hashes: tuple[str, ...] = (), dbc_hashes: tuple[str, ...] = (), parsing_policy: str = 'decoded-results', worker_config: str = 'single-thread', dependency_versions: tuple[tuple[str, str], ...] = (), limitations: tuple[str, ...] = (), software_version: str = '0.1.0.dev0', device_label: str = 'pending', signal_bindings: tuple[chronaxis.core.binding.SignalDefinition, ...] = (), preset_bindings: tuple[chronaxis.results.binding_metadata.PresetBindingMetadata, ...] = (), can_sources: tuple[chronaxis.results.can_metadata.CANSourceMetadata, ...] = (), session_ids: tuple[str, ...] = (), text_can_sources: tuple[chronaxis.results.text_can_metadata.TextCANSourceMetadata, ...] = (), threshold_durations: tuple[chronaxis.results.threshold_metadata.SummaryThresholdDuration, ...] = (), detailed_diagnostics: bool = False, retain_work: bool = False, input_diagnostics: tuple[chronaxis.results.input_diagnostics.InputDiagnostic, ...] = (), trace_requested: bool = False, integrity_diagnostics: bool = False, frame_format_notices: tuple[tuple[str, chronaxis.results.can_metadata.CANFrameFormatNotice], ...] = (), analysis_outcome: chronaxis.results.analysis_outcome.AnalysisOutcome | None = None) -> None
```

### Properties and data fields

| Name | Type | Required | Default | Purpose, choices, and effect |
|---|---|---|---|---|
|`run_id`|str|Yes|None|Unique run identity associated with published manifests and resource records.|
|`input_identity`|str &#124; None|Yes|None|Trace summary for actual input reading. None means no such summary was supplied, not that content was verified.|
|`plan_hash`|str|Yes|None|SHA-256 identity of plan declarations. Actual backend overrides are recorded separately.|
|`backend`|str|Yes|None|Actual backend: reference or numpy. Recorded from effective runner settings; callers normally do not construct this result field.|
|`config_version`|int|Yes|None|Actual analysis structure version: native integer 3, not preset or software version. Version 1 and Boolean values are rejected.|
|`source_time_interpretation`|str|Yes|None|Description of source time coordinates, units, and conversion conventions.|
|`session_boundaries`|tuple[tuple[str, int, int], ...]|Yes|None|Actual (session_id, start_ns, end_ns) tuples. Times are integer nanoseconds with half-open ranges. An empty tuple means boundaries were not established, not an observed zero-duration session.|
|`started_at`|str|Yes|None|Runner-generated timezone-aware ISO 8601 run start, e.g. 2026-10-27T19:00:00+08:00. This is not the first sample timestamp.|
|`mapping_hashes`|tuple[str, ...]|No|()|Recorded mapping-identity digests; empty when not applicable. Empty does not mean verified.|
|`dbc_hashes`|tuple[str, ...]|No|()|Recorded DBC digests; empty when not applicable.|
|`parsing_policy`|str|No|'decoded-results'|Name of the parsing/access policy used.|
|`worker_config`|str|No|'single-thread'|Description of worker settings. A single-thread label is not a performance guarantee.|
|`dependency_versions`|tuple[tuple[str, str], ...]|No|()|Recorded (name, version) dependency tuples.|
|`limitations`|tuple[str, ...]|No|()|Known limitations for this run, retained in published metadata.|
|`software_version`|str|No|'0.1.0.dev0'|Software version, separate from design and configuration versions.|
|`device_label`|str|No|'pending'|Actual content-origin device label; do not infer home/work from a file path.|
|`signal_bindings`|tuple[[SignalDefinition](../../reference/chronaxis.core.binding.md#api-SignalDefinition), ...]|No|()|Complete signal definitions for the run, without samples or input rows.|
|`preset_bindings`|tuple[[PresetBindingMetadata](../../reference/chronaxis.results.binding_metadata.md#api-PresetBindingMetadata), ...]|No|()|Original preset versions and resolved roles.|
|`can_sources`|tuple[[CANSourceMetadata](../../reference/chronaxis.results.can_metadata.md#api-CANSourceMetadata), ...]|No|()|Tuple of CANSourceMetadata. Each item can describe sclicer-functions-v1 single-BLF source name, original/DBC paths, channel, frame count, endpoints, and unit checks. Supplied explicitly by a RunMetadata caller; public AnalysisRunner does not populate it. Default () means details were not supplied, not that CAN input was absent. Check nonempty before reading metadata.can_sources[0].source or .frame_count.|
|`session_ids`|tuple[str, ...]|No|()|Explicit session identities when no time range was requested; does not fabricate boundaries.|
|`text_can_sources`|tuple[[TextCANSourceMetadata](../../reference/chronaxis.results.text_can_metadata.md#api-TextCANSourceMetadata), ...]|No|()|Tuple of TextCANSourceMetadata, describing can-text-v1 source, inputs (path, parser, offset_ns), DBC digests, record counts, and observation times. Explicitly caller-supplied; public AnalysisRunner does not populate it. Default () means details were not supplied. Check nonempty before reading metadata.text_can_sources[0].inputs or .record_count; an empty tuple does not establish empty input.|
|`threshold_durations`|tuple[[SummaryThresholdDuration](../../reference/chronaxis.results.threshold_metadata.md#api-SummaryThresholdDuration), ...]|No|()|Threshold-preset duration summaries. Each SummaryThresholdDuration has preset_id, rule_id, value, unit, and status. A partial value counts only known seconds, not a complete total. Empty when no such preset applies.|
|`detailed_diagnostics`|bool|No|False|Whether extra detailed fields are serialized in the manifest: True includes applicable detail, False uses summaries. This result-model field cannot be edited to retroactively perform missing analysis.|
|`retain_work`|bool|No|False|Explicit request to retain work files; false by default.|
|`input_diagnostics`|tuple[[InputDiagnostic](../../reference/chronaxis.results.input_diagnostics.md#api-InputDiagnostic), ...]|No|()|Requested information about inputs needed in this run.|
|`trace_requested`|bool|No|False|Whether diagnostics.trace was enabled. Actual rows are read through the result trace iterator.|
|`integrity_diagnostics`|bool|No|False|Whether diagnostics.integrity requested input-integrity summaries. Independent of row tracing.|
|`frame_format_notices`|tuple[tuple[str, [CANFrameFormatNotice](../../reference/chronaxis.results.can_metadata.md#api-CANFrameFormatNotice)], ...]|No|()|Verified frame-format differences are always reported, independently of optional diagnostics.|
|`analysis_outcome`|[AnalysisOutcome](../../reference/chronaxis.results.analysis_outcome.md#api-AnalysisOutcome) &#124; None|No|None|AnalysisOutcome accumulated during this run, or None. Reports events, unmet conditions/durations, no observations, or insufficient data per rule, and counts complete/partial/indeterminate calculation rows. None means this path did not supply a summary, not no events; completed means execution finished. No second scan or row trace is performed.|

Source: [`src/chronaxis/results/manifest.py:28`](../../../../src/chronaxis/results/manifest.py#L28) (line numbers refer to `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`).

<a id="api-RunMetadata-estimated_bytes"></a>
### `RunMetadata.estimated_bytes`

Estimates metadata and temporary-object cost before asdict/JSON copying.

```python
RunMetadata.estimated_bytes() -> int
```

Parameters: no explicit arguments.


#### Parameter notes

None.

#### Returns

Conservative byte estimate.

#### Raises

None expected; types have already been validated.

Return type: int。

Source: [`src/chronaxis/results/manifest.py:199`](../../../../src/chronaxis/results/manifest.py#L199) (line numbers refer to `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`).

<a id="api-RunMetadata-to_dict"></a>
### `RunMetadata.to_dict`

Returns independent JSON-compatible metadata. The caller must reserve estimated_bytes before copying.

```python
RunMetadata.to_dict() -> dict
```

Parameters: no explicit arguments.


#### Parameter notes

None.

#### Returns

Independent JSON-compatible dict. Default detailed_diagnostics=False emits the run summary and applicable optional summaries. Nonempty signal_bindings/preset_bindings/can_sources do not cause those detailed keys to appear. True expands detailed models, still omitting empty optional details according to their rules. See [Run metadata](../results.md#metadata-output) for both modes and key examples.

#### Raises

No expected exception; the caller must account for estimated_bytes before copying.

Return type: dict。

Source: [`src/chronaxis/results/manifest.py:210`](../../../../src/chronaxis/results/manifest.py#L210) (line numbers refer to `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`).
