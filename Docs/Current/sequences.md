# 请求响应配对

请求响应配对用来判断每次请求是否在规定时间内收到响应，并区分“已等到超时”和“数据不足，无法判断”。结果记录两次事件的时间及响应延迟。





`sequences`位于根级列表，引用已定义的请求点规则和响应点规则，输出配对结果及等待结论。先通过`rules`产生点事件，再配置等待范围；不能在start/response中直接填信号名。

例如请求在1秒发出，允许0—2秒内响应；3秒收到响应，延迟2秒，仍算成功。如果没有响应，需要区别“确实等满2秒没响应”和“响应记录缺了，无法知道有没有响应”。这就是`sequences`处理的问题。

本页未另行说明的秒数例子采用默认actual。配置intervals为fixed或dbc时，持续确认、等待到期、变化窗口和配对delay_ns使用所选周期依据；原时间坐标和信号到期仍按实际记录时间。先看[三种时间依据对照](intervals.md#timing-basis)。

## 完整最小例与三种结果

[sequence-minimal.yaml](examples/sequence-minimal.yaml)包含请求、响应信号及两条点规则。1秒请求、2秒响应，允许延迟0～2秒，得到matched且delay_ns=1000000000。

[sequence-outcomes.yaml](examples/sequence-outcomes.yaml)延长输入到8秒，在1、3、6秒发出请求：1秒请求由2秒响应配对；3秒请求等到5秒仍无响应，得到no_response；6秒请求等待期间，7秒起响应值缺失，到8秒得到indeterminate。它还显式限制最多2个待响应请求；这不是主动丢弃旧请求的策略。

两个文件均可直接运行`chronaxis run 文件名.yaml --output 结果目录`。最小例只配置必要字段；扩展例用于区分设备没响应和无法判断是否响应。

## 配置片段

本页主字段表相对于`sequences[]`，例如`sequences[].name`。子对象另行注明，表中的字段不能直接放到配置根级。

假设`request`、`response`已经声明为bool信号、单位`1`，并且使用同一时间基准：

应用位置：以[teaching-base.yaml](examples/teaching-base.yaml)为基础，在文件根级加入或替换`rules, sequences`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

```yaml
rules:                         # 列出识别活动或瞬间变化的规则；每项产生有独立ID的事件
  - name: request_edge         # 窗口或计算引用的规则名称
    condition: request         # 填写由已定义信号组成的真假条件；按要检测的业务情况设置
    rule_type: rising_edge     # 选择活动或变化识别算法；本例condition由false变为true时产生瞬时事件
  - name: response_edge        # 窗口或计算引用的规则名称
    condition: response        # 填写由已定义信号组成的真假条件；按要检测的业务情况设置
    rule_type: rising_edge     # 选择活动或变化识别算法；本例condition由false变为true时产生瞬时事件
sequences:                     # 把请求事件与响应事件按允许等待时间配对
  - name: pair                 # 为请求响应配对取唯一名称；结果通过此名区分配对任务
    start: request_edge        # 选择请求事件规则；填写前面rules的name
    response: response_edge    # 选择响应事件规则；填写前面rules的name
    max_delay: 2s              # 设置响应的最大允许延迟；依据协议或业务要求填写，不能小于min_delay
```

|字段|数据类型|必填|省略时的值|可填写的值及用途|
|---|---|---|---|---|
|name|字符串|是|无|命名这组配对结果，供结果表区分任务；由配置作者取唯一名称。本组配对的名字，例如`pair`，用于在输出中区分不同配对；不能与其他配对重名。|
|start|字符串|是|无|选择产生请求事件的点规则；从上方rules[].name取得。已定义的请求点规则名称，例子中填`"request_edge"`。这里填规则名，不是信号名或表达式。|
|response|字符串|是|无|选择产生响应事件的点规则；从上方rules[].name取得。已定义的响应点规则名称，例子中填`"response_edge"`。两条规则必须使用能够对齐的时间。|
|min_delay|时长字符串|否|0s|规定请求到响应的最短允许时长；从设备协议或试验要求取得。大于等于0，例如`"100ms"`：请求后不到100毫秒的响应不能与该请求配对。填`"0s"`时可同刻响应。|
|max_delay|时长字符串|是|无|规定请求到响应的最长允许时长；从响应截止要求取得。不能小于min_delay。例如`"2s"`：请求后恰好2秒的响应仍可配对，超过2秒则不能。|
|max_pending|整数|否|`65536`|限制等待中的请求数，控制内存占用；按预计并发数量设置。大于0；最多同时保存多少个等待响应的请求。超过时报错，不丢掉旧请求，也不会自动把它们判成超时。|

`start`和`response`所引用的规则种类可以是`rising_edge`（由假变真）、`falling_edge`（由真变假）或`start_only`（按其重复触发设置产生点）。`condition_duration`、`hysteresis`、`debounce`、`start_end`描述的是一段活动，`window_delta`本版也未接入配对，不能填入这两个字段。

可在本配对的interval对象中选择实际时间差、固定周期或DBC周期，省略时继承intervals.default。详见[计算间隔](intervals.md)。

本例省略min_delay和max_pending，分别采用0s和65536；只有需要限制最短等待时间或并发数量时才填写。

## 多个请求同时等待时

程序把一个响应交给**最早发出且当前仍在允许时间范围内的请求**；一个响应只用一次。这种“先来的先处理”方式叫FIFO。请求在1秒、2秒发出，响应在3秒到达，两者都允许0—3秒响应时，3秒的响应配给1秒请求，2秒请求继续等。

请求和响应恰好在同一时刻出现时，只要min_delay为0，就可以配对；文件里哪一列先出现不影响这个判断。响应恰好在截止时刻出现，也会先尝试匹配，不会提前把请求记为没有响应。

## 配对结果

|status|实际含义|delay_ns/response|
|---|---|---|
|matched|找到一个符合时间范围的响应|填写所选时间依据下的延迟与响应事件|
|no_response|等待期间响应条件一直能判断，但一直没有响应点|None|
|indeterminate|等待期间响应信号缺失、过期，或记录提前结束，无法下结论|None|

仍以允许0～2秒内响应为例：

|请求时刻|随后发生什么|结果|
|---|---|---|
|第1秒|第3秒收到响应。|matched，延迟2秒。|
|第4秒|第5秒起响应数据缺失，直到截止仍没有可配对的响应点。|第6秒判为indeterminate，无法确定设备是否响应。|
|第7秒|第9秒收到响应。|matched，延迟2秒。|
|第10秒|持续观测到第12秒，期间响应条件可判断，但没有响应点。|no_response，已等满2秒。|

没有请求时，不会生成配对结果，也不会输出一条延迟为0的记录。

以下Python片段放在已创建的`AnalysisResult`上下文内，完整资源管理示例见[Python用法](api-usage.md)。

```python
rows = result.iter_sequences()
try:
    for row in rows:
        delay_s = None if row.delay_ns is None else row.delay_ns / 1_000_000_000
        print(row.request_id, row.response_id, row.status, delay_s, row.decided_ns)
finally:
    rows.close()
```

decided_ns是作出判定的时刻，request_id和response_id关联事件。需要请求的发生时刻时，通过事件ID查events表的confirmed_ns；配对行不嵌套复制整个事件。详见[SummarySequenceRow](reference/chronaxis.results.summary.md#api-SummarySequenceRow)。

## 跨来源配对的同步要求

如果请求记录器在试验开始计0秒，响应记录器晚2秒才计0秒，那么响应文件的1秒实际是请求文件的3秒。要把响应来源加`offset="2s"`并声明对应的同步依据。不能把两份文件都命名为同一个time.clock就当成实际同步；具体配置见[时钟例子](inputs.md)。程序支持已知固定偏移，不自动估计时钟误差或漂移。

如果两个来源是无关试验，它们不能配对；分别作为[独立任务](batch.md)运行。

想少写两条上升沿规则，可使用`command_response`预设，全部参数见[预设](presets.md)。低层状态机和独立参考实现也全部列在[sequence](reference/chronaxis.core.sequence.md)与[sequence_reference](reference/chronaxis.core.sequence_reference.md)，通常直接用AnalysisRunner即可。
