# Python公开API索引

按调用任务查询公开入口。每个名称进入单独的公开对象页，包含完整构造签名、公开方法/属性、参数、返回值和异常。下列名称均可从`chronaxis`导入；结果行模型见[结果结构](reference/chronaxis.results.summary.md)，内部模块见[开发参考](reference/index.md)。从文件运行的完整流程见[Python快速开始](api-usage.md)。

## 计划加载与检查

|公开名称|定义与用途|
|---|---|
|`chronaxis.AnalysisPlan`|[AnalysisPlan](public-api/AnalysisPlan.md#api-AnalysisPlan)：保存一个会话的分析配置，以及静态检查得到的对象。|
|`chronaxis.load_analysis_plan`|[load_analysis_plan](public-api/load_analysis_plan.md#api-load_analysis_plan)：读取JSON/YAML配置及一层公共定义，按各自声明目录解释相对来源路径。|
|`chronaxis.validate_analysis_plan`|[validate_analysis_plan](public-api/validate_analysis_plan.md#api-validate_analysis_plan)：报告静态配置有效性及当前读取、执行和发布能力限制。|
|`chronaxis.explain_analysis_plan`|[explain_analysis_plan](public-api/explain_analysis_plan.md#api-explain_analysis_plan)：列出计划依赖、各节点计算方式、历史需求和预算声明。|
|`chronaxis.PlanValidationError`|[PlanValidationError](public-api/PlanValidationError.md#api-PlanValidationError)：保存配置字段路径、原因、机器错误码及可选的原文定位和修正建议。|

## 执行与结果

|公开名称|定义与用途|
|---|---|
|`chronaxis.AnalysisRunner`|[AnalysisRunner](public-api/AnalysisRunner.md#api-AnalysisRunner)：保存可选后端覆盖，复用同一静态校验，逐次创建独立运行资源。|
|`chronaxis.AnalysisResult`|[AnalysisResult](public-api/AnalysisResult.md#api-AnalysisResult)：保存暂存路径和小型元数据，无events/segments/calculations全量列表。|
|`chronaxis.OutputManifest`|[OutputManifest](public-api/OutputManifest.md#api-OutputManifest)：保存成功发布目录、清单和固定白名单表行数；legacy只在启用时出现。|
|`chronaxis.RunMetadata`|[RunMetadata](public-api/RunMetadata.md#api-RunMetadata)：保存运行身份、实际后端、时间解释、会话边界与兼容限制。|
|`chronaxis.AnalysisError`|[AnalysisError](public-api/AnalysisError.md#api-AnalysisError)：表示分析或结果交付失败；异常本身不承诺旧输出已回滚。|
|`chronaxis.ResultClosedError`|[ResultClosedError](public-api/ResultClosedError.md#api-ResultClosedError)：表示结果已经关闭，不能再创建迭代器、读取或发布。|

## 批量任务

|公开名称|定义与用途|
|---|---|
|`chronaxis.BatchPlan`|[BatchPlan](public-api/BatchPlan.md#api-BatchPlan)：保存批量选项及独立任务列表；任务可引用分析配置路径或已加载的分析计划。同一连续会话仍放在一个任务中。|
|`chronaxis.BatchJob`|[BatchJob](public-api/BatchJob.md#api-BatchJob)：声明一个独立分析；同会话连续文件应包含在本任务的一个计划中。|
|`chronaxis.BatchJobResult`|[BatchJobResult](public-api/BatchJobResult.md#api-BatchJobResult)：保存一个任务的最终状态；发布后关闭失败仍为failed，并保留已发布路径。|
|`chronaxis.BatchReport`|[BatchReport](public-api/BatchReport.md#api-BatchReport)：按原任务顺序汇总结果；每个任务数值表仍在各自目录，不会把不同任务的数值相加。|
|`chronaxis.BatchRunner`|[BatchRunner](public-api/BatchRunner.md#api-BatchRunner)：通过process_count设置分析工作进程数，每次run创建并回收本批的工作进程；不跨批次缓存计划和状态。|
|`chronaxis.load_batch_plan`|[load_batch_plan](public-api/load_batch_plan.md#api-load_batch_plan)：读取严格批量JSON/YAML。参数: path为UTF-8配置文件。返回: BatchPlan。异常: 带路径配置错误。|
|`chronaxis.run_batch`|[run_batch](public-api/run_batch.md#api-run_batch)：运行并发布批量报告。|

## 业务预设

|公开名称|定义与用途|
|---|---|
|`chronaxis.PresetSpec`|[PresetSpec](public-api/PresetSpec.md#api-PresetSpec)：保存预设实例名、任务类型、模板版本、角色与信号对应关系及业务参数；通过from_dict建立不可修改的声明。|
|`chronaxis.PlanFragment`|[PlanFragment](public-api/PlanFragment.md#api-PlanFragment)：保存预设生成的公共节点，不含来源、执行器或真实样本。|
|`chronaxis.build_preset`|[build_preset](public-api/build_preset.md#api-build_preset)：校验v1预设并展开公共声明，不执行I/O或数值分析。|
|`chronaxis.resolve_preset_roles`|[resolve_preset_roles](public-api/resolve_preset_roles.md#api-resolve_preset_roles)：先使用role_bindings明确指定的信号；未指定的角色再按semantic_id和semantic_contract_version查找唯一符合角色要求的信号。|

## 时间转换

|公开名称|定义与用途|
|---|---|
|`chronaxis.TimeConversion`|[TimeConversion](public-api/TimeConversion.md#api-TimeConversion)：保存规范时间及来源精度，避免跨任务修改转换诊断。|
|`chronaxis.TimeOverflowError`|[TimeOverflowError](public-api/TimeOverflowError.md#api-TimeOverflowError)：时间坐标、偏移后坐标或非负跨度超出int64时拒绝运算。|
|`chronaxis.checked_add_ns`|[checked_add_ns](public-api/checked_add_ns.md#api-checked_add_ns)：为一个纳秒坐标添加固定偏移，并检查结果是否仍在int64范围内。|
|`chronaxis.convert_time`|[convert_time](public-api/convert_time.md#api-convert_time)：按明确单位换算纳秒，并在最终结果处取最近偶数舍入。|
|`chronaxis.parse_datetime_ns`|[parse_datetime_ns](public-api/parse_datetime_ns.md#api-parse_datetime_ns)：将ISO完整日期转换为UTC整数纳秒，保留亚微秒分数。|
|`chronaxis.parse_duration`|[parse_duration](public-api/parse_duration.md#api-parse_duration)：解析带单位的非负持续参数，允许显式零长度。|
|`chronaxis.shift_times_reference`|[shift_times_reference](public-api/shift_times_reference.md#api-shift_times_reference)：逐项独立计算固定偏移，作为数组内核的整数真值参考。|
|`chronaxis.time_deltas_reference`|[time_deltas_reference](public-api/time_deltas_reference.md#api-time_deltas_reference)：计算非递减整数时间的相邻跨度，允许同时间不同样本。|

## 功能与配置关联

|配置或任务|功能指南|主要API|
|---|---|---|
|配置文件与公共定义|[配置结构](configuration.md)、[公共定义](imports.md)|load_analysis_plan、AnalysisPlan.from_dict|
|事件、窗口和计算|[规则](rules.md)、[窗口](windows.md)、[计算](calculations.md)|AnalysisRunner.run、AnalysisResult迭代方法|
|独立任务批量运行|[批量任务](batch.md)|load_batch_plan、run_batch|
|预设角色及声明生成|[业务预设](presets.md)|PresetSpec、resolve_preset_roles、build_preset|
|时间单位和日期|[时间与结果质量](concepts.md)|parse_duration、convert_time、parse_datetime_ns|
