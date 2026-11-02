"""把预设合成活动/片段/指标逐行暂存，再发布两后端结果用于手算对照。

输入复用presets_demo中[0,6)s的400V/10A及20A合成数据，来源、单位和方向
声明见该例。核心仍使用完整内存样本；结果层使用两行缓冲和共享预算，
本例专门展示结果层组合，不测全进程RSS。输出新建在专用work目录，
活动能量8000J/16000J，电量20As/40As按Wh/Ah展示；关闭保留发布文件。
元数据使用实际设备环境标签及synthetic；本例不读取真实CAN或触发旧raw writer。
"""

# 生成全新专用目录，参数不会删除或覆盖任何旧目录。
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4
import numpy as np
from chronaxis.results import AnalysisResult, RunMetadata, ResourceBudget, ResultSpool
from chronaxis.results.summary import SummaryEventRow, SummarySegmentRow, SummaryCalculationRow
from presets_demo import run_example


def build_result(work_dir: Path, backend: str) -> AnalysisResult:
    """把独立公共核心的已计算结果交给结果层，不重复输入读取。

    参数: work_dir为全新专用目录，backend为reference/numpy。
    返回: AnalysisResult；调用者负责close。异常: 核心/预算/IO错误直接传播。
    """
    bindings, fragment, activities, calculations, alarm_events, segments = run_example(False, backend, 2)
    # 新结果层账本只覆盖本层；完整内存输入是明确演示限制。
    spool = ResultSpool(ResourceBudget(1048576), work_dir, result_buffer_rows=2,
                        requested_tables=('events', 'segments', 'calculations'))
    sequence = 0
    try:
        for event in (*activities, *alarm_events):
            spool.append(SummaryEventRow(sequence, 'demo', 'entity', 'session', event.rule.rule_id,
                event.event_id, event.start_ns, event.confirmed_ns, event.end_ns, event.status,
                event.trigger_kind, event.quality))
            sequence += 1
        for segment in segments:
            spool.append(SummarySegmentRow(sequence, 'demo', 'entity', 'session', segment.window.window_id,
                segment.segment_id, segment.actual.start_ns, segment.actual.end_ns, segment.status,
                segment.parent_event_ids, segment.quality))
            sequence += 1
        # 每活动两个明确指标，父ID取真实事件身份，不能凭数值或时间猜。
        for event_index, event in enumerate(activities):
            for calculation_index in range(len(fragment.calculations)):
                calculation = calculations[event_index * len(fragment.calculations) + calculation_index]
                spool.append(SummaryCalculationRow(sequence, 'demo', 'entity', 'session', calculation.spec.calculation_id,
                    calculation.spec.operation, 'event', event.event_id, calculation.value, calculation.unit,
                    calculation.status, calculation.reason, calculation.quality))
                sequence += 1
        spool.seal()
        metadata = RunMetadata('result-demo-' + backend, bindings.identity, 'synthetic-direct-composition-v1',
                               backend, 3, 'relative ns; common synthetic origin',
                               (('session', 0, 6_000_000_000),), datetime.now(timezone.utc).isoformat(),
                               dependency_versions=(('numpy', np.__version__),),
                               limitations=('synthetic only', 'full-memory core composition',
                                            'new-layer estimate is not whole-process RSS'), device_label=os.environ.get('CHRONAXIS_DEVICE_LABEL', 'pending'))
        return AnalysisResult(spool, metadata, 'jsonl')
    except BaseException:
        spool.close()
        raise


def main() -> None:
    """运行两后端、核对手算与完整typed结果，并导出到全新目录。

    参数: CLI可选--work-dir为专用父目录。返回: None，打印结果/资源/文件路径。
    异常: 任何不一致、预算或输出错误传播，不覆盖已有目录。
    """
    parser = argparse.ArgumentParser(description='合成结果暂存/发布演示，保留全部输出')
    parser.add_argument('--work-dir', type=Path, default=Path('work/m2-result-demo'))
    args = parser.parse_args()
    root = args.work_dir.absolute() / uuid4().hex
    outputs = []
    reference_rows = None
    for backend in ('reference', 'numpy'):
        with build_result(root / (backend + '-spool'), backend) as result:
            # 本例仅有12结果行，为对照临时收集；产品公共结果没有全量列表字段。
            rows = (tuple(result.iter_events()), tuple(result.iter_segments()), tuple(result.iter_calculations()))
            if reference_rows is None:
                reference_rows = rows
            else:
                assert rows == reference_rows
            assert len(rows[0]) == 5 and len(rows[1]) == 3 and len(rows[2]) == 4
            # 指标表按calculation_id和父ID稳定排列；用窗口映射核对手算而非依赖当前行序。
            expected = {0: (8000/3600, 20/3600), 3_000_000_000: (16000/3600, 40/3600)}
            events = {event.event_id: event for event in rows[0]}
            for row in rows[2]:
                index = 0 if row.unit == 'Wh' else 1
                assert abs(row.value - expected[events[row.parent_id].start_ns][index]) < 1e-12
            manifest = result.write(root / (backend + '-output'))
            outputs.append({'backend': backend, 'status': manifest.status, 'rows': dict(manifest.row_counts),
                            'manifest_path': str(manifest.manifest_path), 'resources': result.spool.budget.snapshot()})
    print(json.dumps({'device_label': os.environ.get('CHRONAXIS_DEVICE_LABEL', 'pending'), 'synthetic': True, 'results': outputs}, ensure_ascii=False, indent=2))


# 导入只提供函数；直接执行才创建本例独立目录。
if __name__ == '__main__':
    main()
