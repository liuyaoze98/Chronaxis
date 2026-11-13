# 配置字段规范

这里的 JSON Schema 是机器可以读取的字段说明：它告诉编辑器哪些字段能填写、字段类型、必填项、允许值及结构约束。文件采用 JSON 保存，但同时适用于解析后的 YAML 和 JSON 配置对象。

| 配置用途 | 字段规范 | 实际加载入口 |
|---|---|---|
| 单次分析 | [analysis.schema.json](analysis.schema.json) | `load_analysis_plan` |
| 独立任务批量清单 | [batch-v1.schema.json](batch-v1.schema.json) | `load_batch_plan` |
| 公共来源/信号/派生定义 | [definitions.schema.json](definitions.schema.json) | 主配置的imports显式引用；不单独运行 |

当前分析结构只接受整数 `config_version: 4`；独立任务清单使用 `batch_version: 1`，两个字段控制不同对象，不能互换。公共定义和批量规范通过同目录相对路径引用当前分析规范，无需远端下载。

## 看懂字段说明

例如，`valid_for: 500ms` 表示一条有效样本最多沿用 500 毫秒。到期即未知，无效更新会覆盖前值。`timeout: 5s` 表示开始后允许等待的上限，两者用途不同。

规范中的 `required` 是必须明确填写的字段；`description` 说明含义与限制；`enum` 列出允许选择的值；`examples` 提供写法示例。示例数值不代表设备推荐参数。`default` 仅说明省略该项时程序采用什么，编辑器或校验器不应因此自动把它写入配置。

缺省行为有些依赖上下文，不能表示成一个固定值。例如`valid_for`省略时按可用的信号周期推导；CAN信号可从DBC补齐输入单位。具体推导与缺项处理见[信号字段](../Current/signals.md)。省略与显式`null`按各字段说明处理，不能一律填成`null`。

同名字段在不同位置可能有不同含义。`signals[].conversion.offset`是数值换算的加数，`sources[].time.offset`是时间偏移；导出设置中的`window`引用已声明的分析窗口。规范在相应位置分别说明。

## 编辑器关联与验证

支持 YAML Language Server 格式的编辑器可以在 YAML 文件顶部使用注释关联规范。例如文件位于仓库 `examples/` 中时：

```yaml
# yaml-language-server: $schema=../Docs/Schema/analysis.schema.json
config_version: 4  # 当前分析配置结构版本
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

三份规范使用 Draft 2020-12。标准验证器离线注册文件 URI，并跟随本地相对引用。字段注解应跟随实际解析器和模型同步，不因规范中的说明而新增运行行为。

实际字段填写与输入边界见[输入来源](../Current/inputs.md)和[配置教程](../Current/configuration.md)。编辑器界面中的悬浮提示尚未逐个实测，不能把标准验证器通过写成特定编辑器已验收。

| 时间 | 修改者 | 内容 |
|---|---|---|
| 2026-11-11T11:00:28+08:00 [home] | liuyaoze | AUDIT-FIX-02：同步BOM默认及ASC解析版本说明、英文译文；补齐Schema入口在此前版本4/移除INI整改中漏同步的正文，保留历史记录。 |
| 2026-10-25 | liuyaoze | CFG-READ-01/E1：新增字段规范入口、上下文与默认行为说明、本地引用及验证边界。 |

- 2026-10-26T00:02:32+08:00 | CFG-READ-01/G | 同步公共定义及当前入口行为；liuyaoze。

- 2026-10-27T13:13:00+08:00 | DOC-CURRENT-02/A2 | 信号可空元数据与12种value_map边界对齐解析器；派生字段省略合法但显式null仍拒绝；definitions/批量/INI通过本地引用继承，fixed上限不变；liuyaoze。
