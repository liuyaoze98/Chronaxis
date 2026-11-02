"""观察条件从True变为False时，持续活动与下降沿分别怎样记录。

合成布尔信号在0纳秒为True，3纳秒真实更新为False，有效期为10纳秒，
来源观测到3纳秒。连续分析范围[0,3)；3纳秒实际更新仍参加点上的判断。
duration规则要求连续成立3纳秒，活动从0开始、3确认并在真实False处关闭；
falling规则在3纳秒产生下降沿点事件，点事件end_ns为null。
main让参考和NumPy各自构建时间轴、计算条件、处理确认时刻并检测事件，
参考每批一行，NumPy每批两行；输出完整事件字段及两者是否一致。
需NumPy及PYTHONPATH=src；只向标准输出打印，不读取历史文件，不作性能承诺。
"""

# stdout记录可检查，不写缓存或原始资源。
import json
# 已实现当前typed内存模型及标准库参考链。
from chronaxis.core import (MemoryRow, SessionSpec, SignalBindings, SignalDefinition, SignalDType,
                            SourceSpec, TemporalRule, TimebaseSpec, TimeType, compile_expression,
                            build_timeline_reference, detect_memory_reference)
# 数组后端显式加载，不让通用导入依赖NumPy。
from chronaxis.core.temporal_memory_numpy import detect_memory_numpy


def main():
    """分别检测持续活动和下降沿，并比较不同切批的完整事件。

    参数: 无；使用[0,3)纳秒连续域、真实3纳秒末点及10纳秒有效期。
    返回: None；JSON打印时间轴、活动、点事件及两后端是否一致。
    异常: 配置、绑定、模型或执行错误传播；UNKNOWN不能静默变为False。
    """
    # 时钟原点为合成身份，不假设真实设备同步。
    clock = TimebaseSpec('clock', TimeType.RELATIVE, 'temporal-demo-v1')
    # 终点真实更新FALSE不能被EOF丢掉。
    source = SourceSpec('sensor', clock, (MemoryRow(0, {'raw_flag': True}, 0), MemoryRow(3, {'raw_flag': False}, 1)),
                        observation_start_ns=0, observation_end_ns=3)
    # 连续半开，点域包含3ns真实末点。
    session = SessionSpec('session', clock, 0, 3, (source,))
    # 通用BOOL无领域语义目录依赖。
    bindings = SignalBindings(session, (SignalDefinition('flag', 'sensor', 'raw_flag', SignalDType.BOOL, '1', 10),))
    # 只编译已绑定简单别名，不动态eval。
    compiled = compile_expression('flag', bindings)
    # 两规则scope/identity各自完整，实例不会共享候选。
    rules = (TemporalRule('active', 'demo', 'session', 'condition_duration', 3), TemporalRule('exit', 'demo', 'session', 'falling_edge'))
    # 每规则分别执行完整参考与真实数组链。
    reference = tuple(event for rule in rules for event in detect_memory_reference(compiled, rule, batch_rows=1))
    # 相同输入没有读取/解码重复调用，仅已声明memory原行。
    array = tuple(event for rule in rules for event in detect_memory_numpy(compiled, rule, batch_rows=2))
    # 身份/quality/来源也参与一致性比较，不仅事件数。
    result = {'input_id': 'temporal-demo-v1', 'backends_equal': reference == array,
              'timeline_ns': [tick.time_ns for tick in build_timeline_reference(compiled, rules[0]).ticks],
              'events': [{'event_id': event.event_id, 'event_type': event.event_type, 'start_ns': event.start_ns,
                          'confirmed_ns': event.confirmed_ns, 'end_ns': event.end_ns, 'status': event.status,
                          'quality': int(event.quality), 'dependency_quality': int(event.dependency_quality)} for event in reference]}
    # JSON null明确point end，不用零长度活动冒充point。
    print(json.dumps(result, ensure_ascii=False))


# 导入仅提供示例入口，不自动执行或写文件。
if __name__ == '__main__':
    # 仅直接运行才打印完整可检查结果。
    main()
