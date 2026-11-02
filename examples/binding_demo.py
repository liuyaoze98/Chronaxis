"""把原字段raw.current绑定为表达式别名pack_current，并展示声明变化后的身份。

本例使用合成身份synthetic-binding-v1，0纳秒处原电流为1000 mA。
SignalDefinition声明乘以0.001后使用A，有效期为10纳秒，可选语义名称为
battery.current。SignalBindings负责记录字段引用和声明，main只打印JSON：
alias是表达式使用的名称，field保留原字段，identity_changed表示把有效期
改成20纳秒后绑定身份发生变化。本例不执行单位换算；预期换算值1 A需在
数值处理入口计算。输入来自局部内存，只向标准输出打印，无文件读写。
运行需将src加入PYTHONPATH；具体绑定接口见chronaxis.core.binding。
"""

# JSON仅输出本示例诊断，不宣称公开产品manifest schema。
import json
from dataclasses import replace

# 导入真实绑定入口，不使用未实现的产品AnalysisRunner。
from chronaxis.core import (MemoryRow, SessionSpec, SignalBindings, SignalDefinition, SignalDType,
                            SourceSpec, TimebaseSpec, TimeType)


def main() -> None:
    """构造电流绑定，打印原字段定位和有效期变化后的身份。

    参数: 输入为文件顶部声明的合成电流、单位系数和10纳秒有效期。
    返回: None；标准输出为JSON，identity_changed应为True。
    异常: 声明或绑定不合法时传播对应错误；本函数不执行原值换算。
    """
    # 明示合成公共起点，不猜真实设备时间。
    clock = TimebaseSpec("clock", TimeType.RELATIVE, "synthetic-binding-v1")
    # 已解码内存原字段有点号，原值不再次施加DBC转换。
    source = SourceSpec("sensor", clock, (MemoryRow(0, {"raw.current": 1000}, 0),))
    # 会话域由调用者声明，来源字段在实际行中存在。
    session = SessionSpec("demo_session", clock, 0, 10, (source,))
    # 这里只声明mA到A的系数；真正转换原值由后续数值处理入口完成。
    definition = SignalDefinition("pack_current", "sensor", "raw.current", SignalDType.FLOAT64,
                                  "A", 10, input_unit="mA", scale=.001, semantic_id="battery.current")
    # 当前绑定冻结真实来源和所有声明身份。
    bindings = SignalBindings(session, (definition,))
    # 新定义有效期变化不能复用旧执行身份。
    changed = SignalBindings(session, (replace(definition, valid_for_ns=20),))
    # 当前会话完整字段引用实际可解析。
    reference = bindings.source_ref("pack_current")
    # 只输出已实施事实，不假报表达式执行或数值结果。
    result = {"sample_id": "bindings-demo-v1", "alias": definition.name, "field": reference.field,
              "session_id": reference.session_id, "semantic_id": definition.semantic_id,
              "input_unit": definition.input_unit, "unit": definition.unit, "scale": definition.scale,
              "unit_status": definition.unit_status, "identity_changed": bindings.identity != changed.identity}
    # 诊断输出可读JSON，stdout之外没有副作用。
    print(json.dumps(result, ensure_ascii=False, indent=2))


# 显式直接调用示例才运行，不在import时构造会话。
if __name__ == "__main__":
    # 保持最小实际入口，不生成产品计划占位。
    main()
