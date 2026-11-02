# 编辑器字段提示

JSON Schema是供编辑器与校验器读取的字段规范。规范文件用JSON保存，同时描述YAML和JSON解析后的同一配置结构。它提供字段名、类型、必填项及允许值提示；跨字段引用、单位、同步和实际执行能力仍以Chronaxis检查结果为准。

## 选择对应规范

| 配置文件 | 可下载的本地规范 |
|---|---|
| 单次分析config_version: 3 | [analysis.schema.json](../Schema/analysis.schema.json) |
| 批量batch_version: 1 | [batch-v1.schema.json](../Schema/batch-v1.schema.json) |
| sources/signals/derived公共定义 | [definitions.schema.json](../Schema/definitions.schema.json) |
| INI映射mapping_version: 1 | [legacy-import-v1.schema.json](../Schema/legacy-import-v1.schema.json) |

将四份文件保存在同一目录，保持文件名，以便规范之间的相对引用工作。离线HTML包也包含这四份文件，不需要访问作者电脑。

## YAML编辑器关联

支持YAML Language Server配置方式的编辑器可识别下列顶部注释。假设plan.yaml旁边有schemas目录，其中保存上述规范：

下面仅演示文件顶部的编辑器设置。请把第一行注释加到已有的完整分析配置开头，并保留原来的dataset、sources、signals等内容；不要用这两行替换整份配置。

```yaml
# yaml-language-server: $schema=schemas/analysis.schema.json
config_version: 3    # 声明分析文件采用的字段结构版本；当前填写整数3
```

这是关联方式片段，不是完整分析文件。注释中的路径相对于plan.yaml；移动文件后应调整。JSON可通过编辑器的文件关联设置选择规范，具体界面取决于编辑器。不要把`$schema`作为业务配置字段加入文件，Chronaxis会拒绝未声明字段。

## 命令行检查

编辑器提示不代替加载器。对自己的完整配置执行：

```powershell
chronaxis validate plan.yaml
chronaxis explain plan.yaml
```

重复键、锚点、别名、标签、多文档和非有限数由配置解析器检查；有效期、单位和依赖由计划检查继续核对。检查通过仍不证明输入文件内容或业务阈值正确。
