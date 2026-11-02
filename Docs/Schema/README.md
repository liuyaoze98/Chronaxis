# 配置字段规范

这里的 JSON Schema 是机器可以读取的字段说明：它告诉编辑器哪些字段能填写、字段类型、必填项、允许值及结构约束。文件采用 JSON 保存，但同时适用于解析后的 YAML 和 JSON 配置对象。

| 配置用途 | 字段规范 | 实际加载入口 |
|---|---|---|
| 单次分析 | [analysis.schema.json](analysis.schema.json) | `load_analysis_plan` |
| 独立任务批量清单 | [batch-v1.schema.json](batch-v1.schema.json) | `load_batch_plan` |
| 公共来源/信号/派生定义 | [definitions.schema.json](definitions.schema.json) | 主配置的imports显式引用；不单独运行 |
| 旧 INI 的显式映射 | [legacy-import-v1.schema.json](legacy-import-v1.schema.json) | `load_legacy_ini` 的 mapping 文件 |

当前分析结构只接受 `config_version: 3`。批量清单的 `batch_version: 1` 和 INI 映射的 `mapping_version: 1` 各有独立用途，不能互换。映射规范通过同目录相对路径引用当前分析规范；不需要旧版本文件、远端下载或旧 URN 注册。

## 看懂字段说明

例如，`valid_for: 500ms` 表示一条有效样本最多沿用 500 毫秒。到期即未知，无效更新会覆盖前值。`timeout: 5s` 表示开始后允许等待的上限，两者用途不同。

规范中的 `required` 是必须明确填写的字段；`description` 说明含义与限制；`enum` 列出允许选择的值；`examples` 提供写法示例。示例数值不代表设备推荐参数。`default` 仅说明省略该项时程序采用什么，编辑器或校验器不应因此自动把它写入配置。

缺省行为有些依赖上下文，不能表示成一个固定值。例如计算项的 `partial_policy` 继承 `execution.partial_policy`，`input_unit` 省略时使用该信号的 `unit`。这些行为写在说明中，不能一律填成 `null`。开始/结束规则的 `emit_initial` 默认开启，普通边沿规则默认关闭；持续条件和稳定性规则不提供这个字段。

同名字段在不同位置可能有不同含义。`signals[].offset` 是数值加数，`sources[].time.offset` 是时间偏移；变化量规则的 `window` 是回看时长，导出设置的 `window` 是窗口 id。规范在相应位置分别说明。

## 编辑器关联与验证

支持 YAML Language Server 格式的编辑器可以在 YAML 文件顶部使用注释关联规范。例如文件位于仓库 `examples/` 中时：

```yaml
# yaml-language-server: $schema=../Docs/Schema/analysis.schema.json
config_version: 3
```

这里是说明关联方式的片段，不是完整可运行计划。注释中的路径相对于这个 YAML 文件；放在其他目录时必须调整路径。JSON 文件可通过编辑器的文件关联设置选择对应规范；不要向业务配置中插入 `$schema` 字段，实际加载器会严格拒绝未声明字段。

命令行以程序实现为最终依据：

```text
chronaxis validate examples/analysis_plan.json
chronaxis explain examples/analysis_plan.json
chronaxis validate examples/analysis_plan.json --format json
```

规范负责字段结构；程序继续检查跨字段引用、单位、信号同步、整数原生类型、纳秒范围和当前执行能力。YAML 的重复键、锚点、别名、标签、多文档以及非有限数由共享解析器检查，不能用结构规范替代语法检查。静态通过不证明 CSV 列、DBC、真实数据覆盖或内存峰值已验证。

## 维护与验证依据

四份规范使用 Draft 2020-12。标准验证器离线注册文件 URI，并跟随本地相对引用；不恢复旧分析结构的兼容入口。字段注解应跟随实际解析器和模型同步，不因规范中的说明而新增运行行为。

本次覆盖检查、约束对照、默认值和实际配置例的验证记录见[CFG-READ-01 验证报告](../Verification/CFG-READ-01.md)。编辑器界面中的悬浮提示尚未逐个实测，不能把标准验证器通过写成特定编辑器已验收。

| 时间 | 修改者 | 内容 |
|---|---|---|
| 2026-10-25 | liuyaoze | CFG-READ-01/E1：新增字段规范入口、上下文与默认行为说明、本地引用及验证边界。 |

- 2026-10-26T00:02:32+08:00 | CFG-READ-01/G | 同步公共定义及当前入口行为；liuyaoze。

- 2026-10-27T13:13:00+08:00 | DOC-CURRENT-02/A2 | 信号可空元数据与12种value_map边界对齐解析器；派生字段省略合法但显式null仍拒绝；definitions/批量/INI通过本地引用继承，fixed上限不变；liuyaoze。
