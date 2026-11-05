# 事件窗口与片段



`windows`位于配置根级，根据已定义的规则事件生成分析或导出的时间片段。窗口可以向事件前后扩展或合并相邻范围；生成片段不会改写原事件及其真实活动区间。

<a id="window-fields"></a>
本页未另行说明的秒数例子采用默认actual。配置intervals为fixed或dbc时，持续确认、等待到期、变化窗口和配对delay_ns使用所选周期依据；原时间坐标和信号到期仍按实际记录时间。先看[三种时间依据对照](intervals.md#timing-basis)。

## 完整最小例与合并扩展

[window-minimal.yaml](examples/window-minimal.yaml)自带按钮在1、3、6秒按下的记录，上升沿规则在这三个时刻生成点，窗口向后取3秒，得到[1,4)、[3,6)、[6,9)三段。

[window-merged.yaml](examples/window-merged.yaml)只增加`merge: overlap_and_adjacent`，把重叠或相接范围合成[1,9)。规则仍产生三个点，片段保留三个父事件ID。[window-exit-delay.yaml](examples/window-exit-delay.yaml)则把按钮按下定义为活动，用`merge: exit_delay`在每次活动结束后等待2秒；原活动为[1,2)、[3,4)、[6,7)，片段合为[1,9)；原活动与合并后片段分别保留。

运行方式：`chronaxis run window-minimal.yaml --output 结果目录`。配置都包含来源和信号，不依赖后文的活动教程。

## 窗口配置：windows

<a id="activity-context-example"></a>
### 活动前后各取1秒并计算能量

沿用[温度活动的例子](rules.md#duration-selection-origin)：温度第1秒达到80，第3秒确认已保持2秒，第6秒降到80以下。现在想把开始前、结束后各1秒的数据一起拿来分析。

先给这个窗口起名 `hot_context`，再让能量计算项使用它：

应用位置：以[activity.yaml](examples/activity.yaml)为基础，在文件根级加入或替换`windows, calculations`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。 基础文件已定义hot规则及temperature、power信号；先读[来源与信号](activity-tutorial.md)。

```yaml
windows:                     # 围绕已定义规则的事件选取时间片段，供计算或导出使用
  - name: hot_context        # 计算或导出引用的窗口名称
    rule: hot                # 引用前面定义的事件规则
    pre: 1s                  # 设置起点之前保留多久上下文；0s表示不提前
    post: 1s                 # 设置结束点之后保留多久上下文；0s表示不延长
calculations:                # 本例的统计结果
  - name: context_energy     # 结果表中的计算名称
    scope:                   # 选择计算范围；session整段会话，{rule: 名称}逐事件，{window: 名称}逐片段
      window: hot_context    # 按指定窗口的每个片段分别计算；填写前面windows中的name
    operation: integral      # 按有效持续时间积分
    expr: power              # 使用已定义的信号或公式
```

这是完整计划中的两部分配置；`hot` 规则和 `power` 信号须已定义。每个设置各做一件事：

- `rule: "hot"`：使用hot规则找到的活动。
- 自动推导的 `anchor: "activity"`：从活动实际开始和结束的时刻向两边扩展。
- `pre: "1s"`、`post: "1s"`：开始前取1秒、结束后取1秒，所以本例窗口为第0秒到第7秒。
- `scope: {window: hot_context}`：对这个窗口中的数据计算能量，每个窗口分别得到一个结果。

假设第0秒到第7秒都有有效记录，功率始终为10W，那么能量是10×7＝70J。把hot规则的 `selection_origin` 在 `"onset"` 和 `"confirmed"` 之间切换，这个窗口仍是第0秒到第7秒，能量仍为70J。

如果改用 `scope: {rule: hot}`，计算的就是活动本身：`"onset"` 对应50J，`"confirmed"` 对应30J。

### 窗口的全部字段

本页主字段表相对于`windows[]`，例如`windows[].name`。子对象另行注明，表中的字段不能直接放到配置根级。

|字段|数据类型|必填|默认值|可填写的值与含义|
|---|---|---|---|---|
|name|字符串|是|无|命名窗口定义，供calculations[].scope.window或outputs.signal_csv.scope.window、outputs.can_frames.scope.window引用；由配置作者取唯一名称。窗口名称，如 `"context"`。|
|rule|字符串|是|无|选择由哪条规则提供事件；从上方rules[].name取得。填写已有规则的name，如 `"hot"`。|
|anchor|字符串|否|由规则事件种类确定|选择按活动起止区间还是触发点向外取数据；依据规则的输出类型选择。`"activity"`：围绕整段活动扩展；`"point"`：围绕一个触发时刻扩展。须与规则产生的事件类型一致。|
|pre|时长字符串|否|0s|设置窗口向前扩展的时长；按需要观察的事件前过程填写。向事件开始或触发点之前多取多久，大于或等于0。|
|post|时长字符串|否|通常0s；start_only沿用window_duration|设置窗口向后扩展的时长；按需要观察的事件后过程填写。向活动结束或触发点之后多取多久，大于或等于0。point窗口的pre/post至少有一项大于0。|
|merge|字符串|否|`"none"`|控制同一窗口定义生成的片段是否合并；根据是否要分别计算每次事件选择。多段窗口如何合并，四种值见下表。|
|exit_delay|时长字符串|merge为exit_delay时必填；其他模式不填|无|控制活动结束后保留片段及接纳下一次活动的等待时间；按允许的活动间隔填写。活动结束后等待多久再结束片段，大于或等于0。需anchor=activity且post=0，避免向后扩展两次。|

|merge填写值|含义|例子|
|---|---|---|
|`"none"`|各片段分别保存，重叠也不合并。|0～3秒和2～5秒仍是两段。|
|`"overlap"`|有重叠时间才合并。|0～3秒和2～5秒合为0～5秒；0～2秒与2～5秒仍分开。|
|`"overlap_and_adjacent"`|重叠或首尾相接都合并。|0～2秒与2～5秒也合为0～5秒。|
|`"exit_delay"`|活动结束后继续等待；等待期间开始下一次活动，就把它们放进同一个片段。|活动为0～1秒和2～3秒，exit_delay为3秒时得到0～6秒片段，原活动仍是两次。|

选择 `anchor` 时，根据规则产生的事件类型填写：

|使用的规则|anchor填什么|
|---|---|
|condition_duration、debounce、hysteresis、start_end|`"activity"`，围绕整段活动。|
|rising_edge、falling_edge、window_delta|`"point"`，围绕一次触发时刻。|
|start_only|`"point"`；另外，post必须等于该规则的window_duration。|

窗口可在自身interval对象中选择时间依据，省略时继承intervals.default；字段见[计算间隔](intervals.md)。

## 配置错误与边界

引用不存在的rule、anchor与事件类型不符、point窗口前后都为0、exit_delay与post组合冲突时，计划检查会指出具体字段。窗口超出请求/观测范围时不会产生虚构数据；读取片段范围、完整性及原因，再决定是否接受计算结果。
