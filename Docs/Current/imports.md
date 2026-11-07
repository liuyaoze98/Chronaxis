# 公共来源与信号定义

同一套信号要用于多份分析时，把来源、信号绑定和派生表达式放进公共文件。每份主配置仍各自声明分析对象、时间范围、事件规则和计算项。它们共享的是定义，不共享运行状态、数据缓存或结果。

主配置用根级`imports`列表引用公共文件。公共文件只包含sources、signals和derived；不嵌套导入。加载入口load_analysis_plan负责展开，输出仍是普通AnalysisPlan。

## 运行完整例子

本页使用快速开始的合成CAN记录：[0,6)秒的能量是38J。公共文件另定义double_power = power * 2，所以同一范围的double_energy为76J。全部输入与两个配置已经保存：

~~~text
examples/
  analysis-imports.yaml
  shared/definitions.yaml
  data/can/quickstart.asc
  data/can/teaching.dbc
~~~

这里的examples指[当前手册的examples目录](examples.md)。在仓库根执行：

~~~powershell
New-Item -ItemType Directory -Force work | Out-Null
python -m chronaxis validate Docs/Current/examples/analysis-imports.yaml
python -m chronaxis explain Docs/Current/examples/analysis-imports.yaml
python -m chronaxis config origins Docs/Current/examples/analysis-imports.yaml
python -m chronaxis config resolve Docs/Current/examples/analysis-imports.yaml --defaults --output work/independent.yaml
python -m chronaxis run work/independent.yaml --output work/imports-result
~~~

两次分析的结果目录可以复用，自动增加时间文件名；后面的config resolve导出配置仍需使用新文件路径。[imports_example.py](examples/imports_example.py)会自动创建独立工作目录，分别用reference（参考实现）和numpy（数组实现）运行并核对38J和76J；随后导出独立配置，移除本次复制的公共文件，再运行导出的配置。两种实现的区别见[运行设置](execution.md)；执行命令为python Docs/Current/examples/imports_example.py。

## 主配置怎样引用

[完整主配置](examples/analysis-imports.yaml)通过如下字段引用公共文件：

~~~yaml
imports: [shared/definitions.yaml]    # 先加载公共定义文件；列表项为相对当前配置文件的路径
~~~

imports是可选的文件路径数组；省略或填写空数组表示不引入外部定义。只接受明确的本地.json/.yaml/.yml文件，大小写后缀均支持；不支持URL、通配符、环境变量替换或目录扫描。路径可以是绝对路径，或相对主配置所在目录的路径。JSON与YAML文件可混用。

[公共文件](examples/shared/definitions.yaml)只包含sources、signals、derived中的至少一个字段，不填写config_version，不添加新包装：

~~~yaml
sources:                                 # 列出输入来源；每项规定数据位置、格式和时间解释方式
  - name: bus                            # 给本来源取计划内唯一名称；下方signals.source引用这个名称
    paths: ../data/can/quickstart.asc    # 选择输入文件、连续分卷列表或目录；相对路径基于本配置，目录按自然序读取
    dbc_by_channel:                      # 为每个CAN通道指定解码用DBC文件；键是通道编号的字符串
      '1': ../data/can/teaching.dbc      # 为这个通道指定DBC文件；路径相对当前配置文件，通道键须为字符串
signals:                                 # 把输入字段定义为有名称、类型、单位和有效期的分析信号
  - name: power                          # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                               # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x100'                  # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: Power                      # 填写DBC中的信号名称，大小写须一致
derived:                                 # 用已定义信号的表达式生成新信号；先定义再在后续功能中引用
  double_power:                          # 定义名为double_power的派生信号，后面的计算通过此名称引用
    expr: power * 2                      # 规定派生值如何由已有信号计算；名称必须先在signals或前面的derived中定义
~~~

公共定义需要显式name，供导入时检查重名和按名称覆盖；这是与普通单文件配置的区别。本例只有一个来源，各信号的source可省略。ASC格式、相对秒时间、信号类型和单位均可确定，因此不重复填写。

sources与signals是数组；derived是名称到表达式对象的映射。每项派生表达式只需expr；unit默认从公式和输入单位推导，需要明确声明时再填写。公共文件不能包含另一个imports，也不能声明dataset、rules、calculations、执行设置或输出设置。

## 合并顺序与重名

程序按imports列表的顺序读取定义，然后追加主文件中的本地定义。每组定义保持原顺序；同名声明不会互相覆盖，也不递归合并。来源名必须唯一，signals与derived共用一套名称，任意两处重名都报错，即使内容完全相同。重复导入同一文件也不会自动去重。

例如先导入power，主文件又声明power，错误会指向主文件的那项声明，并说明首次声明的位置。若只想改变本次任务的有效期，可使用下面的overrides；重复声明同名信号仍然报错。跨文件的信号引用、派生表达式依赖、单位与循环依赖仍由同一静态校验检查。

## 为本次任务调整公共定义

主文件可以用overrides按已有名称修改少量参数。例如公共power从DBC取得1秒周期，默认有效期为3秒，本次只允许沿用1秒：

```yaml
imports: [shared/definitions.yaml]  # 先加载公共定义文件；列表项为相对当前配置文件的路径
overrides:                          # 明确覆盖导入的公共定义；仅在需要改动已导入设置时填写
  signals:                          # 按已导入信号的名称指定允许覆盖的设置
    power:                          # 修改名为power的已导入信号；其他字段保持原定义
      valid_for: 1s                 # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
```

下表的对象属于根级overrides，下一层按已有名称索引，例如`overrides.signals.power.valid_for`；不同于根级signals声明列表，不能把overrides.signals写成数组。

|对象|允许覆盖的字段|
|---|---|
|sources|path、paths、dbc_by_channel、time、reader|
|signals|dtype、unit、valid_for、period、conversion、choices、valid_range、invalid_values、sample_policy、same_time_policy|
|derived|expr、unit|

每个字段整体替换。例如覆盖time时，应提供本次需要的完整time对象；遗漏的子字段采用通常默认值，不保留公共文件里的旧子字段。path与paths只保留本次选择的一个。覆盖中的数据和DBC相对路径以主文件为起点。

不能在overrides中新增对象、改名、改signal绑定或写任意metadata。覆盖后仍检查信号引用、单位和字段取值。错误和config origins会指向实际覆盖位置，而不是已被替换的公共值。没有填写overrides时仍使用原公共定义。

## 路径和错误位置属于声明文件

公共文件shared/definitions.yaml中的../data/can/quickstart.asc相对于shared目录解释，最终指向examples/data/can/quickstart.asc；teaching.dbc也按该公共文件所在目录定位。来源path、paths内每个文件，以及dbc_by_channel内的DBC路径都遵循这一规则；metadata中的自由文本不会被改成路径。

错误指向真正声明字段的文件、原索引及行列。例如公共文件中的valid_for填成0s，消息指向definitions.yaml的有效期字段。缺少字段时指向最近父对象，不能给不存在的字段捏造行列。

查看定义来源：

~~~text
python -m chronaxis config origins Docs/Current/examples/analysis-imports.yaml
python -m chronaxis config origins Docs/Current/examples/analysis-imports.yaml --fields --format json
~~~

默认列来源、信号、派生定义及其文件位置；--fields改为逐项列出用户实际写入、合并后仍生效的字段，例如signals[0].unit。--format默认text；选择json时，报告结构如下。

|位置|字段|含义|
|---|---|---|
|报告根级|configuration|本次查询的配置文件路径|
|报告根级|configuration_type|配置种类，例如分析或批量|
|报告根级|scope|本次按定义还是按字段查询|
|报告根级|items|查询条目列表|
|items中的每项|effective_path|展开导入、应用覆盖后的字段位置|
|items中的每项|declared_path|该字段在原声明文件中的位置|
|items中的每项|file、line、column|声明文件，以及从1开始的行号和列号|
|items中的每项|name|定义名称；逐字段查询时为null|
|来源定义条目|resolved_paths|数据文件与DBC实际指向的路径|

程序补出的默认值没有用户声明位置，因此不会虚构来源。逐字段模式只列位置，不复制字段值。这个命令只读配置；普通分析不会自动生成来源报告。

## 导出与其他入口

config resolve展开全部导入和预设，去掉imports、已应用的overrides与已展开的presets，固定数据/DBC的绝对路径（不解析符号链接或目录联接的真实目标），重新校验后写新文件。导出的配置不再依赖公共定义文件；它仍需要原业务输入可访问，也不会复制原始日志或DBC。跨设备使用时须让相应数据路径可用。config convert只改变JSON/YAML表示，保留imports及路径文本，因此仍依赖公共文件；含相对路径时只能输出到同目录。

批量配置本身不支持imports，每个子计划可以独立使用；批量的origins列出批量声明的任务或模板路径，不代替各分析配置的来源报告。

Python的load_analysis_plan读取主文件与显式公共定义。AnalysisPlan.from_dict只接收已展开的原生字典；遇到imports会拒绝并提示使用文件入口或config resolve。成功计划保存普通展开声明，不保存行列表或第二份配置原文。

编辑器为公共文件关联[definitions.schema.json](../Schema/definitions.schema.json)，主配置关联[analysis.schema.json](../Schema/analysis.schema.json)。跨文件重复和引用仍需运行validate；字段规范不能代替加载后校验。
