# 结果聚合

根级`aggregations`对同一次分析中已经产生的计算行、事件、窗口片段或请求响应结果再次统计。例如先计算每次加载的平均功率，再对两次加载的均值10W和20W求P95，得到19.5W。每次活动贡献一行，按行等权；不会再次按活动持续时间加权。它不读取任意历史CSV，也不合并独立批量任务的结果。

## 先运行完整示例

[power-statistics.yaml](examples/power-statistics.yaml)包含ASC输入、信号、加载规则、逐活动均值和最终聚合。在该文件目录执行`chronaxis run power-statistics.yaml --output result-statistics`，从本轮manifest的outputs找到“聚合结果”表，`load_mean_p95`应为19.5W，候选2、参与2。[全部实际输出](example-results.md#power-statistics-yaml)

以下片段替换该文件根级的`aggregations`；`load_mean`已经由完整文件的calculations定义：

```yaml
aggregations:                 # 对已有结果行再次统计
  - name: load_mean_p95       # 新聚合结果的名称
    source:                   # 只选择一个已命名的结果来源
      calculation: load_mean  # 每段加载的一项平均功率
    operation: quantile       # 对这些均值求分位数
    q: 0.95                   # P95的位置概率
```

## 来源与操作选择

| source 中的唯一字段 | 输入行 | 允许操作 | 数值字段 |
|---|---|---|---|
|calculation: 名称|该标量计算的各结果行；不能引用select|count、sum、mean、variance、quantile、median|数值操作默认value，可省略field|
|sequence: 名称|该配对规则发现的各请求结果|count、sum、mean、variance、quantile、median|数值操作只取成功配对delay_ns，默认可省略field|
|rule: 名称|该规则的事件|count|不填field|
|window: 名称|该窗口的最终片段|count|不填field|

count统计对象数量，不能把它当作时间覆盖率。数值操作按符合要求的结果行统计；请求确认超时与观测不足会分别记录，不把不存在的延迟当0。

## 字段与组合规则

| 字段 | 类型、必填和默认 | 用途与限制 |
|---|---|---|
|name|必填唯一名称|与其他规则、窗口、计算等节点不能重名|
|source|必填对象|仅有上表一个字段，引用同一次分析内已定义的来源|
|operation|必填字符串|按来源从上表选择；sum求和、mean均值、variance方差、quantile分位数、median中位数|
|field|可省略字符串|数值指标只能value，配对数值只能delay_ns；count禁止填写|
|group_by|字符串列表，默认[]|[]把来源行合为一组；不允许重复分组键，见下节|
|unit|可省略单位字符串|数值操作采用来源单位或兼容目标；variance是原单位平方；count只允许单位1|
|q|有限数字，仅quantile必填|0～1（含端点）；P95填0.95。其他操作禁止填写，包括median|
|ddof|整数，仅variance适用，默认0|只允许0或1，以N-ddof作分母；不足时无数值，其他操作禁止填写|
|include_partial|布尔，默认false|仅calculation来源的数值操作允许true，纳入仍有可用数值的部分结果；count和其他来源不能启用|
|partial_policy|report或strict，默认继承execution.partial_policy|report可返回已知部分并标partial；strict在所需数据不足时不给数值|

分位数把参与值升序排列，位置为`(N-1)×q`，相邻位置线性插值；median固定q=0.5。精确分位数需要保存参与值并预留排序空间，受本次内存预算限制。

### 分组键

所有来源可用`dataset_id`、`entity_id`、`session_id`，以及与本来源匹配的`calculation_id`、`sequence_id`、`rule_id`或`window_id`。逐事件／逐窗口计算还可用`parent_id`：它指产生这行计算结果的那次事件或窗口片段。只有确实产生对应事件或片段，才有对应的parent_id组。会话范围计算不能按parent_id分组。独立批量任务分别生成自己的组。

### 空值与完整性

- 已充分观测且没有发生事件时，对该事件来源count为0；没有可求均值的数值时，均值不是0，而是空值。
- 某次事件确实发生，但均值的筛选条件没有选中任何样本，该均值无值，不能作为0参与聚合。完整积分或持续时间为0仍是合法值，可以参与。
- 条件信号中断时，已找到3次事件也不能证明中断期间没有其他事件。`discovery_complete`指出现有观测能否确认全部候选均已识别；它与每项数值是否完整不同。
- 默认不纳入partial数值。开启include_partial也不能使无值、质量不合格或覆盖不足的结果变为有效数据。

输出中`candidate_count = included_count + definition_excluded_count + quality_excluded_count`。例如5次请求，4次成功的延迟为100、200、300、400ms，1次确认超时：成功延迟P95为385ms，候选5、参与4、定义排除1。若最后一次请求没有等到完整截止而日志就结束，应记观测不足；不能称为已确认超时。[结果列及状态](results.md#v4-aggregations)
