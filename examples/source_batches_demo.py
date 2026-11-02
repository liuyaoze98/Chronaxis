"""把内存样例拆成单样本批次，观察什么时候能够宣布某个时刻已完整读取。

输入复用memory_analysis.build_bindings的合成数据、单位、10秒有效期和
0到6秒范围。ReadRequest的batch_rows=1限制每批传输的信号样本总数，
不是每批原始行数；0秒处三个字段因此会跨批次。watermark_ns表示已完整
处理到的时间，source_eof表示来源已结束，进度不能根据单批末样本自行猜测。
main为参考和NumPy各建独立适配器，收集7个小型批次的样本数、进度与结束
标记，打印二者是否一致，并在finally关闭适配器。这里演示来源协议，
分析执行、内存预算及结果发布由上层接口负责。
需NumPy及PYTHONPATH=src；不读写文件，不调用旧CAN模块。
"""

# JSON只输出小规模说明，不保存全部生产结果。
import json
# 从已验证合成任务复用输入，不重新猜测工程阈值。
from memory_analysis import build_bindings
# 当前公开来源和请求是真实已接线接口。
from chronaxis.sources import MemorySourceAdapter, ReadRequest


def main() -> None:
    """逐批读取内存样例，打印两后端的样本数和完整读取进度。

    参数: 无；输入由build_bindings提供，batch_rows为1。
    返回: None；打印7个小批次摘要和两后端是否一致。
    异常: 模型、转换或批次协议错误传播；finally关闭每个适配器。
    """
    # 全部配置与原值已在合成输入明确，不读取DBC。
    bindings = build_bindings()
    # 仅此小示例收集7条进度，不作为生产结果全量模型。
    summaries = {}
    # 每后端独立来源实例，不跨任务继承watermark。
    for backend in ('reference', 'numpy'):
        # 当前来源和definitions都是typed冻结输入。
        adapter = MemorySourceAdapter(bindings.session.sources[0], bindings.session.session_id, bindings.signals, backend=backend)
        # 请求覆盖0到6秒；batch_rows=1按全部信号列的样本总数限制传输批次。
        request = ReadRequest(bindings.session.session_id, tuple(item.name for item in bindings.signals), 0, 6_000_000_000, 1)
        # try/finally关闭实例，即使示例打印准备失败也释放活动请求。
        try:
            # 第一原行3列跨批，只有下一行更晚后watermark=0。
            summaries[backend] = [(batch.sample_count, batch.watermark_ns, batch.source_eof) for batch in adapter.iter_batches(request)]
        finally:
            # close保留原输入，不删除任何文件。
            adapter.close()
    # 输出实际协议事实，profile/schema/AnalysisRunner能力不从这里推断。
    print(json.dumps({'input_id': 'memory-analysis-v1', 'backends_equal': summaries['reference'] == summaries['numpy'], 'batch_rows': 1, 'batches': summaries['numpy']}))


# 入口保护避免import即运行，Windows生命周期明确。
if __name__ == '__main__':
    # 使用同一个实际main，无隐式业务副作用。
    main()
