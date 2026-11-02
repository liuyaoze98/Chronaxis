"""从两张合成信号表读取电流和整数标识，查看跨文件的批次与来源位置。

输入是tests/fixtures/signals下的continuous_1.csv和continuous_2.csv，
按给定顺序组成一个连续来源。time_s以秒解析为纳秒，current_mA乘0.001
转换成A，identifier保持INT64整数；两信号有效期均为10秒。请求范围从
0到6秒，每批最多传输一个信号样本，同一时刻的多个字段可能跨批次。
main分别读取参考和NumPy后端，JSON打印两者是否一致、批次数、最终进度
以及首条记录的文件名和物理行号。watermark_ns表示来源已经完整处理到的
时间，source_eof表示来源读取结束；不能将某一批的最后样本误当完整进度。
本例只读取小型合成夹具，关闭适配器后保留原文件。需NumPy及PYTHONPATH=src；
这里读取的是已解码信号表，CAN接入、公共AnalysisRunner和真实日志验收仍待各自任务。
"""

# 小JSON摘要不承担生产结果全量保存。
import json
# 输入位置相对于实际示例文件，不依赖当前启动目录。
from pathlib import Path
# 明确绑定与时基不会从车型或字段名猜测。
from chronaxis.core.binding import SignalDefinition
# 当前时钟是声明为合成的共同起点。
from chronaxis.core.models import TimebaseSpec
# 大整数与布尔各有独立声明类型。
from chronaxis.core.types import SignalDType, TimeType
# 真正已实现的CSV来源和typed请求。
from chronaxis.sources import ReadRequest, SignalCSVSourceAdapter, SignalCSVSpec


def main() -> None:
    """分别用两个后端读取相同信号表，核对值、位置和最终进度。

    参数: 无；夹具路径相对本文件定位，时间及信号声明见文件顶部。
    返回: None；打印后端对照、批次数和真实文件行引用。
    异常: 文件、时间、列结构或批次协议错误传播；finally关闭适配器。
    """
    # 路径顺序对应一个连续合成来源，不按时间排序文件。
    root = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures' / 'signals'
    # 显式秒列/relative origin，未猜实际工程采样周期。
    spec = SignalCSVSpec('table', (root / 'continuous_1.csv', root / 'continuous_2.csv'), TimebaseSpec('clock', TimeType.RELATIVE, 'csv-continuous-v1'), 'time_s', 's')
    # current_mA额外.001转A，输出大标识保持INT64。
    definitions = (SignalDefinition('current', 'table', 'current_mA', SignalDType.FLOAT64, 'A', 10_000_000_000, input_unit='mA', scale=.001),
                   SignalDefinition('identifier', 'table', 'identifier', SignalDType.INT64, '1', 10_000_000_000))
    # batch1让同时间/同文件尾组必然跨传输边界。
    request = ReadRequest('session', ('current', 'identifier'), 0, 6_000_000_000, 1)
    # 仅本小例收集摘要，产品结果不能用无界列表。
    outputs = {}
    # 每后端新实例，不重复使用旧状态或转换结果。
    for backend in ('reference', 'numpy'):
        # 此普通CSVsource不会调用CAN reader/decoder。
        adapter = SignalCSVSourceAdapter(spec, 'session', definitions, backend=backend)
        # 所有退出路径都关闭句柄。
        try:
            # 摘要包含原文件/物理行/序号/掩码，不混为float宽表。
            outputs[backend] = [(batch.watermark_ns, batch.source_eof,
                                 [(name, column.sequence.tolist(), column.values.tolist(), column.quality.tolist(),
                                   [(Path(ref.path).name, ref.line_number) for ref in column.source_ref]) for name, column in batch.series.items()]) for batch in adapter.iter_batches(request)]
        finally:
            # 关闭实例保留原夹具，不删除文件。
            adapter.close()
    # 数值和实际来源/边界两个后端全部一致。
    print(json.dumps({'input_id': 'csv-continuous-v1', 'backends_equal': outputs['reference'] == outputs['numpy'], 'batches': len(outputs['numpy']),
                      'last_watermark_ns': outputs['numpy'][-1][0], 'source_eof': outputs['numpy'][-1][1], 'first_record': outputs['numpy'][0][2]}, ensure_ascii=False))


# 导入示例不自动读文件，Windows入口保护明确。
if __name__ == '__main__':
    # 直接执行已验证用户流程。
    main()
