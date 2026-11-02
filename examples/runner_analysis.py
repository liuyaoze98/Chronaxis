"""从一张合成功率表找到两次活动，计算能量并发布结果。

运行本文件会在仓库work下建立唯一案例目录：一张0到8秒的CSV、一份完整JSON计划、
本次分析暂存及最终CSV表。功率始终4000W，活动为0—1秒和2—3秒，因此两个事件
各4000J；退出延迟把片段合到0—6秒，包含活动间隔，所以片段为24000J。会话请求
到12秒、实际记录到8秒，会话能量32000J。

只调用公开AnalysisRunner/load_analysis_plan/AnalysisResult；不在例子里实现读取、条件或积分，
不读取旧CAN项目。结果逐行读取并关闭，再write一次发布；结果上下文释放句柄，
合成输入及已发布文件保留，运行暂存按默认设置清理。没有性能或用户真实日志结论。
"""

# 独立例只需标准库和公共包；实际数组依赖在访问计划/AnalysisRunner时按需加载。
import json
from pathlib import Path
from uuid import uuid4
from chronaxis import AnalysisRunner, load_analysis_plan


def main():
    """建立有限合成CSV，核对手算能量，再发布到唯一新目录。

    参数: 无。返回: 实际已发布目录Path。异常: 原计划/分析/发布错误或手算断言失败。
    副作用: 只在新项目work写本案例文件，输入和已发布文件保留；不修改历史快照。
    """
    ns = 1_000_000_000
    root = Path(__file__).resolve().parents[1] / 'work' / 'runner-example' / uuid4().hex
    root.mkdir(parents=True)
    # 单位、每次真实更新和共同起点在首次加载前给出，不用结果反推输入定义。
    rows = ((0, 4000, 1), (1, 4000, 0), (2, 4000, 1), (3, 4000, 0), (8, 4000, 0))
    (root / 'power.csv').write_text('ns,power,active\n' + ''.join(
        f'{second * ns},{power},{active}\n' for second, power, active in rows), encoding='utf-8')
    config = {'config_version': 3,
        'dataset': {'name': 'power_example', 'entity': 'example_device', 'session': 'example_session',
            'domain': {'start': '0s', 'end': '12s'}},
        'sources': [{'name': 'table', 'source_type': 'signal_csv', 'path': 'power.csv', 'time_column': 'ns',
            'time': {'time_type': 'relative', 'unit': 'ns', 'origin': 'example_common'}}],
        'signals': [{'name': 'power', 'source': 'table', 'field': 'power', 'dtype': 'float64',
            'unit': 'W', 'valid_for': '20s'},
            {'name': 'active', 'source': 'table', 'field': 'active', 'dtype': 'int64',
                'unit': '1', 'valid_for': '20s'}],
        'rules': [{'name': 'active_period', 'rule_type': 'condition_duration', 'condition': 'active > 0', 'minimum_duration': '0s'}],
        'windows': [{'name': 'joined', 'rule': 'active_period', 'anchor': 'activity',
            'pre': '0s', 'post': '0s', 'merge': 'exit_delay', 'exit_delay': '3s'}],
        'calculations': [{'name': 'session_energy', 'scope': 'session', 'operation': 'integral', 'expr': 'power', 'unit': 'J'},
            {'name': 'event_energy', 'scope': 'event:active_period', 'operation': 'integral', 'expr': 'power', 'unit': 'J'},
            {'name': 'segment_energy', 'scope': 'segment:joined', 'operation': 'integral', 'expr': 'power', 'unit': 'J'}],
        'execution': {'backend': 'numpy', 'batch_rows': 1, 'result_buffer_rows': 1,
            'memory_budget_bytes': 256 * 1024 ** 2},
        'outputs': {'tables': 'csv'}, 'metadata': {'example': 'runner_analysis', 'data_kind': 'synthetic'}}
    plan_path = root / 'analysis.json'
    plan_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    plan = load_analysis_plan(plan_path)
    runner = AnalysisRunner()
    report = runner.explain(plan)
    assert report.validation.execution_ready and not report.validation.errors
    # run完成表示分析成功；发布是write的独立步骤，这里给两者不同的新目录。
    with runner.run(plan, work_dir=root / 'analysis-work') as result:
        expected = {'session_energy': 32000.0, 'event_energy': 4000.0, 'segment_energy': 24000.0}
        counts = dict.fromkeys(expected, 0)
        reader = result.iter_calculations()
        try:
            for row in reader:
                # 每行直接核手算并显示，不把完整结果表收集进列表。
                calculation_id = row.calculation_id
                assert row.value == expected[calculation_id] and row.unit == 'J'
                counts[calculation_id] += 1
                print(f'{calculation_id}: {row.value:g} J；状态 {row.status}')
        finally:
            reader.close()
        assert counts == {'session_energy': 1, 'event_energy': 2, 'segment_energy': 1}
        manifest = result.write(root / 'published')
        assert manifest.status == 'completed'
        print(f'结果已发布到：{manifest.output_dir}')
    # 上下文已关闭结果并清理运行暂存；输入与发布目录可继续查看。
    return manifest.output_dir


# 仅直接运行才创建合成输入和输出，导入示例不启动分析。
if __name__ == '__main__':
    main()
