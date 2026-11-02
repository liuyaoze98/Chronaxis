"""演示请求后的匹配、缺观测和正常超时三种结果。

全部资料为合成数据，时间单位为秒并明确转为整数纳秒；不需要CAN、DBC或文件。
请求1秒、响应3秒恰好满足2秒上限；请求4秒等待期间观测缺失；请求7秒之后
完整观察到9秒仍无响应。示例通过core入口执行并断言结果，再打印简洁JSON。
此例演示core序列接口；使用配置文件执行任务请参阅AnalysisRunner用法。
"""

# 标准库JSON仅用于展示本次真实运行结果。
import json
from chronaxis.core import ConditionTick, ConditionTimeline, SequenceRule, TemporalRule, pair_sequence
from chronaxis.core.temporal import make_event
from chronaxis.core.types import Truth as T, QualityFlag as Q


def point(second, *, response=False):
    """构造合成请求或响应的已确认点事件。

    参数: second为整数秒；response选择响应角色。
    返回: Event，起点和确认时间相同，保留规则和会话身份。
    异常: 既有模型的输入校验错误传播。
    """
    # 秒只在输入边界转换，核心不使用浮点时间。
    time = second * 1_000_000_000
    event_rule = TemporalRule('response' if response else 'request', 'synthetic', 'session', 'rising_edge')
    return make_event(event_rule, time, time, None, 'point', Q.NONE, Q.NONE, trigger='rising_edge')


def main():
    """运行完整内存配对，核实三个结果并输出秒级摘要。

    参数: 无；使用本文件声明的合成数据。
    返回: None；向控制台输出JSON，不写文件。
    异常: 断言、模型或配对失败直接传播。
    """
    # 响应条件的可判断性覆盖完整区间，4到5秒无观测，10秒为真实EOF。
    ticks = tuple(ConditionTick(second*1_000_000_000,
                                T.UNKNOWN if second in (4, 10) else T.FALSE,
                                Q.MISSING if second in (4, 10) else Q.NONE,
                                terminal=second == 10, point_state=T.UNKNOWN if second == 4 else T.FALSE,
                                point_quality=Q.MISSING if second == 4 else Q.NONE)
                  for second in (0, 1, 3, 4, 5, 7, 10))
    timeline = ConditionTimeline(0, 10_000_000_000, ticks)
    specification = SequenceRule('response_check', 'synthetic', 'session', 'request', 'response', 0, 2_000_000_000)
    results = pair_sequence(specification, tuple(point(t) for t in (1, 4, 7)), (point(3, response=True),), timeline, batch_rows=2)
    # 手算真值独立于JSON展示：决定时间分别3、6、9秒。
    assert [(item.status, item.decided_ns) for item in results] == [('matched', 3_000_000_000), ('indeterminate', 6_000_000_000), ('no_response', 9_000_000_000)]
    assert results[0].delay_ns == 2_000_000_000
    assert results[1].observation_quality == Q.MISSING
    print(json.dumps([{'request_s': item.request.confirmed_ns//1_000_000_000,
                       'status': item.status, 'decided_s': item.decided_ns//1_000_000_000,
                       'delay_ns': item.delay_ns, 'quality': int(item.observation_quality)}
                      for item in results], ensure_ascii=False))


if __name__ == '__main__':
    # 显式入口才执行，不在导入时生成事件或修改文件。
    main()
