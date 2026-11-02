# 配置字段参考

按字段所属模块查询，先在[配置结构](configuration.md)确认放置位置，再到下列页面查看具体类型、默认值、取值及组合条件。机器校验文件用于编辑器和自动验证，不能代替字段的使用说明。

## 怎样读取字段路径

- `dataset.domain.start`：从根级 `dataset` 进入 `domain`，填写其子字段 `start`。点号用于查表，不写进实际键名。
- `signals[]`：信号列表的每一项；`signals[0]`：第一项。实际 YAML 用每项前面的 `-` 表示列表，不写 `signals[]:`。
- “映射/对象”是一组字段和值；“列表/数组”是按顺序排列的多项内容。父字段和子字段用缩进区分，每层2个空格，不用Tab。

完整的多行与内联对照见[配置文件语法](configuration-language.md#field-paths)，2–5秒分析示例见[数据集](dataset.md#只分析2到5秒)。查到字段后，应修改现有父段，不能把完整路径作为新键追加到文件末尾。

## 按根字段查找

|根字段|用途与说明入口|
|---|---|
|config_version|[配置语法与版本](configuration-language.md)|
|dataset|[数据集与分析范围](dataset.md)：普通分析只填name；entity、session、domain、metadata按需填写|
|sources|[数据来源](inputs.md)、[CAN文本输入](text-inputs.md)|
|signals|[信号绑定](signals.md)|
|derived|[表达式](expressions.md)|
|rules|[事件检测规则](rules.md)|
|windows|[事件窗口与片段](windows.md)|
|sequences|[请求响应配对](sequences.md)|
|calculations|[统计与积分](calculations.md)|
|message_calculations|[逐消息累计](message-calculations.md)|
|intervals|[计算间隔](intervals.md)|
|presets|[业务预设](presets.md)|
|execution|[执行配置](execution.md)|
|outputs|[输出配置](exports.md)、[信号导出](signal-exports.md)、[报文导出](can-exports.md)|
|imports、overrides|[公共定义](imports.md)|
|diagnostics、metadata|[执行设置](execution.md)：诊断产物、现场和备注|

程序可使用[完整机器校验规范](reference/configuration-schema.md)检查结构。其定义树中的 `properties`、`required`、`oneOf` 等是校验语法，不是应写入业务配置的字段。API文档中的函数参数也不等同于配置字段；只有标明接收公开配置字典的入口，才使用这里同一套名称和层级。
