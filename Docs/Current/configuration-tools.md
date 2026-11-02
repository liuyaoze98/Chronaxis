# 配置生成、转换与展开

本页介绍`chronaxis config`命令组：init生成带输入的模板，convert转换文件表示，resolve输出已展开的实际配置，origins查询字段来自哪个文件。它们处理配置文件，不执行业务分析。先完成[安装](installation.md)，从终端运行下面命令。

## 配置工具参数

表中的 `SCENE`、`INPUT` 是终端参数占位名称，实际命令换成场景名或文件路径；`--output` 等是命令选项，不能作为YAML字段写入 `analysis.yaml`。选项控制下面列出的子命令；同名选项不能跨命令任意使用。路径由你选择，场景名从`config init --list`取得。

|参数|适用命令|作用、填写方法与省略行为|
|---|---|---|
|SCENE|init|选择要生成的场景名称，例如can-asc或can-blf；必须来自--list。实际生成时必填。|
|INPUT|convert、resolve、origins|指定已有配置文件的路径；必填，相对路径从当前工作目录计算。|
|--list|init|列出全部场景后退出，不跟值，不能同时提供场景或输出目录。|
|--style|init|控制说明多少：annotated是默认完整注释；minimal为同一配置的少注释表示。不会删减功能。|
|--output|init|指定尚不存在的模板目录；实际生成时必填，父目录须存在。|
|--output|convert|指定尚不存在的目标文件，必填；.yaml/.yml写YAML，.json写JSON。相对路径配置应保持同目录。|
|--output|resolve|指定尚不存在的展开文件；省略时打印到终端。文件后缀决定表示格式，父目录须可用。|
|--format|resolve|选择yaml或json；输出到终端默认yaml。写文件时显式值须与后缀一致。|
|--defaults|resolve|开关，不跟值；开启后写出适用的默认值，省略则保留显式声明。只展开能确定的配置默认值；缺少CAN类型、单位或枚举映射时，可能读取所指定DBC补齐。|
|--fields|origins|开关，不跟值；开启后列出各个用户填写字段的位置，省略时按来源、信号、派生定义列出。|
|--format|origins|选择text或json；默认text。json用于程序读取字段来源，不是展开后的分析配置。|

## 生成配置模板

需要让 AI 先按场景选模板或查字段时，可从[版本配套指南](ai-guide.md)取得资料。它引用同一套正式规范，带有离线字段检索、可运行示例和诊断说明。

```text
chronaxis config init --list
chronaxis config init can-asc --output demo
chronaxis validate demo/plan.yaml
chronaxis explain demo/plan.yaml
chronaxis run demo/plan.yaml --output result
```

init的场景名必须来自清单；--output必须是尚不存在的目录，父目录必须存在。默认annotated版本包含逐项注释；--style minimal生成配置内容相同的简洁版。ASC、BLF与批量场景需要的小型合成数据会一起写出；CSV专用场景仍可从清单选择。普通模板不重复写默认值，只有本场景确有用途的业务参数才出现。已有目录即使为空也不覆盖。失败时清理本次创建的内容，无法清理的路径保留在原异常说明中。

can-export和signal-export模板中的metadata.device_label初始为home，表示随包合成示例的制作设备；程序不会自动识别你当前的电脑。把模板用于自己的数据时，应改为本次产出设备对应的标签；当前独立导出只接受home/work，具体约束见[导出说明](exports.md)。模板清单catalog.json自身的device_label和data_kind只描述随包资源来源，不会自动填入运行清单。

生成后，编辑 `demo/plan.yaml` 中现有的对应段，不要把命令或字段表的点号路径粘贴成配置键。缩进、列表及整段替换方法见[配置文件语法](configuration-language.md)。

如需BLF输入，把上面的`can-asc`改为`can-blf`。两者都生成对应DBC与可运行输入；接入自己的日志时只替换文件路径和绑定，不需要先转CSV。

## JSON与YAML互转

```text
chronaxis config convert demo/plan.yaml --output demo/plan.json
```

支持单任务配置3、批量配置1和INI映射配置1，三者是独立入口。convert只改变表示方式，不转换旧结构。类型、数值、键的顺序和路径文本保持；注释不保留。输出后会重新解析检查，大整数和浮点负零也必须保留。目标文件必须不存在。

含相对路径时，convert只允许在同目录输出，否则同一文本可能指向不同文件。要放到另一个目录，用下面的resolve明确固定原文件位置。

## 查看实际采用的配置

```text
chronaxis config resolve demo/plan.yaml
chronaxis config resolve demo/plan.yaml --defaults --format json
chronaxis config resolve demo/plan.yaml --defaults --output elsewhere/effective.yaml
```

resolve先按声明顺序展开一层imports，再把预设生成的派生信号、规则、窗口和计算写成普通声明，删除imports和已展开的presets，避免再次生成重复项。省略--output时，终端仅输出配置文本，默认YAML；--format json切换为JSON，方便重定向或程序读取。写文件时由扩展名确定格式；显式--format与扩展名不一致会报错。

--defaults额外写出适用的执行预算、后端、输出开关、诊断开关、来源解码/CSV设置、信号保持/同刻政策、规则确认设置、计算单位/覆盖门槛/继承政策、序列容量及各节点有效间隔。输出仍采用当前reader、conversion、time.clock、对象scope和节点interval结构。它不会添加无关规则字段、猜业务阈值或在未读DBC时编造周期。CAN省略dtype/unit或enum的choices时，加载计划会读取DBC补齐；显式完整声明不因本功能额外打开DBC。未指定--defaults时保留原显式值。

所有来源文件、DBC和批量子计划路径固定为原声明文件所指的绝对路径（按声明文件所在目录拼接并规范化，不解析符号链接或目录联接的真实目标）；不读取报文或物理量数据，不复制数据，也不更改原文件。目录/通配符需要枚举文件名；缺少CAN元数据的声明可能读取DBC。导出的配置可独立重新加载，并能放到其他目录，但跨设备仍需使这些输入路径可用。显式填默认或展开预设会改变根据配置声明计算的标识哈希，这不表示算法改变。

配置错误退出2，文件错误退出1，取消退出130。既有目标、包括硬链接，均拒绝覆盖。


`origins --fields` 显示的 `signals[0].unit` 是“第一个信号的单位字段”的位置说明，不是字面键名；JSON来源报告是查询结果，也不能当作分析配置运行。

查看定义来自哪里使用config origins INPUT；--fields列用户实际写入的最终取值字段（例如signals[0].unit，不含程序补出的默认值），--format json提供结构化位置。它不写文件，不与resolve配置混合，详细规则见[公共定义](imports.md)。
