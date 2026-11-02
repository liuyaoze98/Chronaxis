"""运行规则及派生信号完整案例，对照手算结果。

命令参数: --output指定新的专用工作目录。返回: 退出码0并输出验证记录。
异常: 运行错误或AssertionError表示配置结果不符，不转换为成功。
"""
from pathlib import Path
import argparse
import json
from chronaxis import AnalysisRunner, load_analysis_plan


def verify(output: Path) -> list[dict]:
    """运行18个配置并检查事件区间、确认时间、片段和计算值。

    参数: output为本次独立工作目录；每个案例使用自己的子目录。
    返回: 每例的文件名、事件秒数及计算值列表。
    异常: 配置/运行原异常或断言失败。每次运行均关闭结果资源。
    """
    root = Path(__file__).parent
    # 区间和数值来自各文件输入的人工推算，不从引擎输出反向生成预期。
    expected = {
        'condition_duration': ([(1, 3, 6)], [(1, 3, 6)], [30]),
        'rising_edge': ([(1, 1, None)], [(1, 1, None)], [10]),
        'falling_edge': ([(5, 5, None)], [(5, 5, None)], [10]),
        'start_only': ([(1, 1, None), (6, 6, None)], [(1, 1, None), (6, 6, None)], []),
        'debounce': ([(1, 1, 5)], [(3, 3, 8)], []),
        'hysteresis': ([(1, 1, 6)], [(2, 2, 7)], []),
        'start_end': ([(1, 1, 5)], [(1, 1, 3)], []),
        'window_delta': ([(12, 12, None)], [(4, 4, None), (12, 12, None)], []),
    }
    report = []
    for kind, (minimum, extended, values) in expected.items():
        for suffix, event_expected in [('minimal', minimum), ('extended', extended)]:
            name = f'rule-{kind}-{suffix}'
            with AnalysisRunner().run(load_analysis_plan(root / f'{name}.yaml'), work_dir=output / name) as result:
                events = sorted(result.iter_events(), key=lambda row: row.start_ns)
                actual = [(e.start_ns / 10**9, e.confirmed_ns / 10**9,
                           None if e.end_ns is None else e.end_ns / 10**9) for e in events]
                assert actual == event_expected, (name, actual, event_expected)
                calculated = [c.value for c in result.iter_calculations()]
                assert calculated == (values if suffix == 'extended' else []), (name, calculated)
                if kind == 'start_end' and suffix == 'extended':
                    assert events[0].status == 'timeout'
                if kind in ('start_only', 'rising_edge', 'falling_edge') and suffix == 'extended':
                    segments = sorted(result.iter_segments(), key=lambda row: row.start_ns)
                    actual_segments = [(r.start_ns / 10**9, r.end_ns / 10**9) for r in segments]
                    assert actual_segments == {'start_only': [(1, 6), (6, 11)],
                                               'rising_edge': [(1, 2)], 'falling_edge': [(5, 6)]}[kind]
                report.append({'file': name + '.yaml', 'events_seconds': actual, 'values': calculated})
    for suffix, value in [('minimal', 4000), ('extended', 16000)]:
        name = f'expression-{suffix}'
        with AnalysisRunner().run(load_analysis_plan(root / f'{name}.yaml'), work_dir=output / name) as result:
            actual = [r.value for r in result.iter_calculations()]
            assert actual == [value], (name, actual)
            report.append({'file': name + '.yaml', 'values': actual})
    return report


def main() -> None:
    """读取--output、运行校核并打印JSON；原始错误直接使进程失败。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=False)
    print(json.dumps(verify(output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
