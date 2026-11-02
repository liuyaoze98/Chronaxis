"""独立生成三种旧INI，公开导入后实际运行并核对手算与重复发布。

输入全部在work/m2-import-example/<uuid>新建，不依赖tests或RefProjects。
legacy_sum用同刻两帧及后续两帧：4000/2000/1000/3000W，原方向+1/-1/0/-1，
显式period=0.1s、factorZ=1，正桶400J、负桶500J；负桶仍加原正贡献，不取绝对值。
single和start_only使用Mode在0/1/3/6秒的0/1/0/0：活动[1,3)、片段[0,5)，
或真实1秒点和[0,3)窗口。valid_for只属于普通分析，不作为legacy消息缓存TTL。

每模式只经load_legacy_ini→write_legacy_import→load_analysis_plan→AnalysisRunner.run。
原BOM/CRLF字节、报告SHA和发布前后静态身份逐一核实；有限typed游标复用同目录
已验收的bounded_rows，所有读取关闭后在同一结果上两次write并比对表bytes。
Result.close成功且预算RAM归零才保存成功summary。这里的RAM是内部估算，
不代表RSS、用户日志验收或旧完整trigger/cache/逐帧关闭行为已经等价。

直接脚本和-m均可执行；main只显示短JSON摘要路径。导入模块不写文件、不开
CAN进程。BLF/DBC可选依赖和NumPy使用运行环境显式配置，不声称已全局安装。
"""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

from chronaxis import AnalysisRunner, load_analysis_plan
from chronaxis.migration import load_legacy_ini
from chronaxis.migration.publication import write_legacy_import

# 脚本与正常包模块两种入口都复用同一有限游标关闭逻辑，不复制旧main或测试代码。
if __package__:
    from .message_energy_analysis import bounded_rows
else:
    from message_energy_analysis import bounded_rows


def create_inputs(root):
    """在唯一新案例根写三字节DBC、四帧BLF及四行信号CSV。

    参数: root为已新建的专用目录。返回: 输入Path字典。
    异常: 可选CAN依赖、实际写入或stop错误；主错优先，关闭副错附note及原writer。
    """
    import can
    directory = root / 'inputs'
    directory.mkdir()
    blf, dbc, csv = directory / 'power.blf', directory / 'power.dbc', directory / 'mode.csv'
    dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
        'BO_ 256 Power: 3 Node\n'
        ' SG_ Power : 0|16@1+ (1,0) [0|65535] "W" Node\n'
        ' SG_ Direction : 16|8@1- (1,0) [-128|127] "raw_direction" Node\n', encoding='utf-8')
    writer, primary = can.BLFWriter(blf), None
    try:
        # 每个元组写一条原报文；前两条同刻，不能因普通历史last_by_sequence而丢消息贡献。
        for second, power, direction in ((0, 4000, 1), (0, 2000, -1), (1, 1000, 0), (2, 3000, -1)):
            payload = power.to_bytes(2, 'little') + bytes((direction & 255,))
            writer.on_message_received(can.Message(timestamp=1700000000.0 + second,
                arbitration_id=256, is_extended_id=False, channel=0, data=payload))
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            writer.stop()
        except BaseException as cleanup:
            if primary is None:
                # 首次stop失败也保同一真实writer，调用方可从原异常继续stop恢复。
                cleanup.example_input_writer_cleanup_owner = writer
                raise
            primary.add_note('合成BLF输入writer.stop附加失败: ' + type(cleanup).__name__)
            primary.example_input_writer_cleanup_owner = writer
    # CSV同样为本例新输入，最后6秒原行是实际EOF，不拿请求7秒伪造来源终点。
    csv.write_text('t,Mode\n0,0\n1,1\n3,0\n6,0\n', encoding='utf-8')
    return dict(blf=blf, dbc=dbc, csv=csv)


def mapping_for(mode, backend, batch_rows, tables, device_label):
    """为一个模式给出完整显式mapping，输入路径只相对其mapping-directory。

    参数: mode为三种导入模式；其余为显式运行、表格式和来源标签。
    返回: 原生JSON字典；不读DBC或真实数据，不从旧INI猜单位、TTL、时基或目录。
    异常: ValueError为内部模式不在公开三项；公开解析继续校验其它声明。
    """
    analysis = dict(config_version=3,
        dataset=dict(name='import_' + mode, entity='synthetic', session='trial',
            domain=dict(start='0s', end='4s' if mode == 'legacy_sum' else '7s')),
        rules=[], windows=[], calculations=[], message_calculations=[],
        execution=dict(backend=backend, batch_rows=batch_rows, result_buffer_rows=1,
            memory_budget_bytes=256 * 1024**2), outputs=dict(tables=tables),
        metadata=dict(device_label=device_label, data_kind='synthetic', example='import_legacy_analysis', import_mode=mode))
    if mode == 'legacy_sum':
        analysis['outputs']['contributions'] = 'full'
        analysis['diagnostics'] = dict(trace=True, integrity=True)
        analysis['sources'] = [dict(name='bus', source_type='can_blf', path='../../inputs/power.blf',
            dbc_by_channel={'0': '../../inputs/power.dbc'}, legacy_profile='sclicer-functions-v1',
            time=dict(time_type='relative', unit='s', origin='synthetic_CAN', offset='-1700000000s'))]
        analysis['signals'] = [dict(name=alias, source='bus',
            field=dict(channel=0,  signal=field, frame_id=256, is_extended=False, is_fd=False),
            dtype='float64', unit=unit, valid_for='1ns', same_time_policy='last_by_sequence')
            for alias, field, unit in (('power', 'Power', 'W'), ('direction', 'Direction', 'raw_direction'))]
        aliases = {'signal_P': 'power', 'Direction': 'direction'}
        sections = {'integral_energy': dict(name='energy', source='bus', unit='J', message_policy='current_message-v1',
            update_message=dict(channel=0, frame_id=256, is_extended=False, is_fd=False),
            parameter_units={'period': 's', 'factorZ': '1'})}
    elif mode in ('sclicer_single', 'sclicer_start_only'):
        analysis['sources'] = [dict(name='table', source_type='signal_csv', path='../../inputs/mode.csv',
            time_column='t', time=dict(time_type='relative', unit='s', origin='synthetic_CSV'))]
        analysis['signals'] = [dict(name='mode_value', source='table', field='Mode', dtype='float64',
            unit='1', valid_for='10s')]
        aliases = {'Mode': 'mode_value'}
        sections = {'TRIGGER_mode': dict(name='active' if mode == 'sclicer_single' else 'start', window_id='slice')}
    else:
        raise ValueError('示例仅支持legacy_sum/sclicer_single/sclicer_start_only')
    return dict(mapping_version=1, path_base='mapping_directory', io_policy='explicit_mapping',
        analysis=analysis, aliases=aliases, sections=sections)


def original_ini(mode):
    """生成明确保BOM/CRLF的原INI，而不是把转换计划当原配置。

    参数: mode为三模式之一。返回: 原bytes，后续原样发布并核SHA。
    异常: ValueError为未知内部模式；不执行旧eval、ConfigManager或logger。
    """
    if mode == 'legacy_sum':
        lines = ('; synthetic current-message energy', '[input]', 'ini_path=old.ini',
            'dbc_path=old.dbc', 'msg_path=old-data/', '[output]', 'log_path=old-log.txt',
            '[integral_energy]', 'signal_P=Power', 'period=0.1', 'factorZ=1.0',
            'expr=signal_P * period * factorZ', 'disjunction=Direction')
    elif mode == 'sclicer_single':
        lines = ('; synthetic single', '[TRIGGER_mode]', 'mode=single', 'pre_sec=1', 'post_sec=2', 'expr=Mode==1')
    elif mode == 'sclicer_start_only':
        lines = ('; synthetic start_only', '[TRIGGER_mode]', 'mode=start_only', 'pre_sec=1',
            'post_sec=99', 'duration_sec=2', 'start_expr=Mode==1')
    else:
        raise ValueError('未知示例模式')
    return b'\xef\xbb\xbf' + ('\r\n'.join(lines) + '\r\n').encode('utf-8')


def convert_mode(directory, mode, mapping, device_label):
    """实际加载两配置、最后发布计划，并回读验证完整静态身份和原字节。

    参数: directory为本模式专用目录；mode/mapping为显式配置；device_label为原标签。
    返回: (已发布计划, 有限迁移事实dict)。异常: 原API/文件或身份断言错误，不返回部分成功。
    """
    config_dir = directory / 'mapping-directory'
    config_dir.mkdir(parents=True)
    ini, mapping_path = config_dir / 'old.ini', config_dir / 'mapping.json'
    content = original_ini(mode)
    ini.write_bytes(content)
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding='utf-8')
    imported = load_legacy_ini(ini, mapping_path, mode=mode, device_label=device_label)
    assert imported.plan is not None and imported.report.status == 'success', imported.report.to_dict()
    assert imported.original_ini == content and imported.report.source_sha256 == sha256(content).hexdigest()
    files = write_legacy_import(imported, directory / 'converted' / 'analysis.json', source_paths=(ini, mapping_path))
    assert files.plan is not None and files.original.read_bytes() == content and ini.read_bytes() == content
    report = json.loads(files.report.read_text(encoding='utf-8'))
    assert report == imported.report.to_dict() and report['device_label'] == device_label
    plan = load_analysis_plan(files.plan)
    # 原静态编译及参数次序都必须跨JSON发布保持，不能只看文件存在或规则个数。
    assert plan.identity == imported.plan.identity == report['plan_identity']
    assert plan.bindings.identity == imported.plan.bindings.identity
    assert tuple(item.expr.identity for item in plan.message_calculations) == tuple(item.expr.identity for item in imported.plan.message_calculations)
    assert tuple(item.expr.bindings.identity for item in plan.message_calculations) == tuple(
        item.expr.bindings.identity for item in imported.plan.message_calculations)
    if mode == 'legacy_sum':
        for item in plan.message_calculations:
            assert tuple((value.name, value.value, value.unit) for value in item.parameters) == (
                ('period', 0.1, 's'), ('factorZ', 1.0, '1'))
    return plan, dict(mode=mode, original_path=str(ini), mapping_path=str(mapping_path),
        original_preserved_path=str(files.original), report_path=str(files.report), plan_path=str(files.plan),
        source_sha256=report['source_sha256'], plan_identity=plan.identity,
        declaration_identity=plan.bindings.identity, issue_count=len(report['issues']),
        original_bytes_preserved=True, published_static_identity_preserved=True)


def read_rows(reader, maximum):
    """复用已验有限游标规则，并核公开closed事实。

    参数: reader为新结果游标；maximum为本合成案例已知上限。返回: 有限tuple。
    异常: 原读取/上限/关闭错误或closed断言，不吞取消，不积无界列表。
    """
    rows = bounded_rows(reader, maximum)
    assert reader.closed
    return rows


def legacy_facts(result):
    """核两桶400/500J与八次实际尝试。参数: 活结果。返回: 有限事实。异常: 手算或关联不符。"""
    assert read_rows(result.iter_events(), 0) == read_rows(result.iter_segments(), 0) == ()
    summaries = read_rows(result.iter_calculations(), 2)
    rows = sorted(read_rows(result.iter_contributions(), 8), key=lambda item: item.sequence)
    traces = {item.original_sequence: item for item in read_rows(result.iter_input_trace(), 4)}
    values = {item.calculation_id: item for item in summaries}
    assert set(values) == {'energy_positive', 'energy_negative'} and len(rows) == 8
    for name, expected, count in (('energy_positive', 400.0, 1), ('energy_negative', 500.0, 2)):
        summary = values[name]
        contributions = [row for row in rows if row.calculation_id == name]
        assert summary.value == expected and summary.unit == 'J'
        assert len(contributions) == 4 and sum(row.value is not None for row in contributions) == count
    assert tuple(item.calculation_id for item in rows) == ('energy_positive', 'energy_negative') * 4
    assert tuple(item.original_sequence for item in rows) == (0, 0, 1, 1, 2, 2, 3, 3)
    assert tuple(item.evaluation_index for item in rows) == (0, 0, 1, 1, 2, 2, 3, 3)
    assert tuple(item.value for item in rows) == (400.0, None, None, 200.0, None, None, None, 300.0)
    assert set(traces) == {0, 1, 2, 3} and traces[0].time_ns == traces[1].time_ns == 0
    for item in rows:
        assert item.reason == ('condition_false' if item.value is None else 'contributed')
    diagnostic, = result.metadata.input_diagnostics
    assert diagnostic.record_count == 4 and diagnostic.source_eof and diagnostic.sha256
    expected_counts = dict(calculations=2, contributions=8, input_trace=4)
    assert result.run_manifest['row_counts'] == expected_counts
    return dict(positive_J=values['energy_positive'].value, negative_J=values['energy_negative'].value,
        evaluation_counts=[4, 4], contribution_counts=[1, 2],
        contributions=[dict(calculation_id=item.calculation_id, original_sequence=item.original_sequence,
            evaluation_index=item.evaluation_index, time_ns=traces[item.original_sequence].time_ns,
            raw_values=json.loads(traces[item.original_sequence].values_json),
            contribution_J=item.value, reason=item.reason) for item in rows], row_counts=expected_counts)


def sclicer_facts(result, mode):
    """核导入活动/点事件和父片段。参数: 结果及模式。返回: 手算事实。异常: 断言。"""
    events, segments = read_rows(result.iter_events(), 1), read_rows(result.iter_segments(), 1)
    assert len(events) == len(segments) == 1
    assert read_rows(result.iter_calculations(), 0) == ()
    event, segment = events[0], segments[0]
    ns = 1_000_000_000
    if mode == 'sclicer_single':
        assert (event.start_ns, event.confirmed_ns, event.end_ns, event.status) == (ns, ns, 3*ns, 'closed')
        expected = (0, 5*ns)
    else:
        assert (event.start_ns, event.confirmed_ns, event.end_ns, event.status) == (ns, ns, None, 'point')
        expected = (0, 3*ns)
    assert segment.status == 'complete' and (segment.start_ns, segment.end_ns) == expected
    assert segment.parent_event_ids == (event.event_id,)
    expected_counts = dict(events=1, segments=1)
    assert result.run_manifest['row_counts'] == expected_counts
    return dict(rule=dict(start_ns=event.start_ns, confirmed_ns=event.confirmed_ns,
        end_ns=event.end_ns, status=event.status, rule_id=event.rule_id),
        segment=dict(actual_ns=list(expected), status=segment.status,
            parent_event_ids=list(segment.parent_event_ids)), row_counts=expected_counts)


def repeated_publish(result, directory, tables):
    """同一已封存结果发布两次，逐表实际bytes相同；不再次run或重读输入来源。

    参数: result为活结果；directory为模式根；tables为csv/jsonl。返回: 两发布路径及表SHA。
    异常: 原发布/文件错误或状态、计数、内容不符；不把失败输出算成功。
    """
    first, second = result.write(directory / 'published-1'), result.write(directory / 'published-2')
    assert first.status == second.status == 'completed' and first.row_counts == second.row_counts
    hashes = {}
    for name, count in first.row_counts:
        left, right = directory / 'published-1' / (name + '.' + tables), directory / 'published-2' / (name + '.' + tables)
        one, two = left.read_bytes(), right.read_bytes()
        assert one == two, name
        hashes[name] = dict(row_count=count, sha256=sha256(one).hexdigest())
    return dict(directories=[str(first.output_dir), str(second.output_dir)], tables=hashes,
        repeated_tables_identical=True)


def run_example(backend='numpy', batch_rows=2, tables='jsonl'):
    """运行独立三模式例，全部手算/身份/发布/关闭通过后才写成功summary。

    参数: backend为reference/numpy；batch_rows为1/2/7；tables为csv/jsonl。
    返回: 有限summary dict，含summary_path和每模式实际事实；所有Result均已close。
    异常: 非法选项、实际I/O/预算/依赖/公开API/断言错误，失败目录保留供定位。
    副作用: 仅在work/m2-import-example/<uuid>新建输入、转换、分析暂存和两发布。
    """
    if type(backend) is not str or backend not in ('reference', 'numpy'):
        raise ValueError('backend必须为reference或numpy')
    if type(batch_rows) is not int or batch_rows not in (1, 2, 7):
        raise ValueError('batch_rows必须为1、2或7')
    if type(tables) is not str or tables not in ('csv', 'jsonl'):
        raise ValueError('tables必须为csv或jsonl')
    root = Path(__file__).resolve().parents[1] / 'work' / 'm2-import-example' / uuid4().hex
    root.mkdir(parents=True)
    inputs = create_inputs(root)
    label = os.environ.get('CHRONAXIS_DEVICE_LABEL', '').strip() or 'pending'
    modes = {}
    for mode in ('legacy_sum', 'sclicer_single', 'sclicer_start_only'):
        directory = root / mode
        plan, migration = convert_mode(directory, mode, mapping_for(mode, backend, batch_rows, tables, label), label)
        # 真实来源定位必须在mapping所在目录迁移正确；CSV是paths tuple，CAN才有path。
        # 配置保词法绝对路径及其原身份，示例只为核物理目标解析其中的../，不改计划。
        if mode == 'legacy_sum':
            assert plan.sources[0].config.path.is_absolute() and plan.sources[0].config.dbc_path.is_absolute()
            assert plan.sources[0].config.path.resolve() == inputs['blf'].resolve()
            assert plan.sources[0].config.dbc_path.resolve() == inputs['dbc'].resolve()
        else:
            assert len(plan.sources[0].config.paths) == 1 and plan.sources[0].config.paths[0].is_absolute()
            assert plan.sources[0].config.paths[0].resolve() == inputs['csv'].resolve()
        runner = AnalysisRunner()
        assert runner.validate(plan).execution_ready
        with runner.run(plan, work_dir=directory / 'analysis-work') as result:
            assert result.metadata.plan_hash == plan.identity and result.metadata.device_label == label
            actual = legacy_facts(result) if mode == 'legacy_sum' else sclicer_facts(result, mode)
            published = repeated_publish(result, directory, tables)
            budget = result.spool.budget
            identity = result.metadata.input_identity
        # 上下文真实close失败会抛原错；仅成功关闭且共享账本0时保存该模式完成事实。
        assert budget.ram_bytes == 0
        modes[mode] = dict(migration=migration, actual=actual, published=published,
            input_identity=identity, device_label=label, ram_after_close=budget.ram_bytes,
            all_bounded_readers_closed=True)
    summary = dict(device_label=label, data_kind='synthetic', backend=backend, batch_rows=batch_rows,
        tables=tables, work_root=str(root), summary_path=str(root / 'summary.json'),
        inputs={name: str(path) for name, path in inputs.items()}, modes=modes,
        manual=dict(legacy_sum_J=dict(positive=400.0, negative=500.0),
            single=dict(activity_ns=[1_000_000_000, 3_000_000_000], segment_ns=[0, 5_000_000_000]),
            start_only=dict(point_ns=1_000_000_000, segment_ns=[0, 3_000_000_000])),
        limitations=['合成输入，不代表用户实际日志验收', 'legacy_sum只用本条字典，period/factor各应用一次，不再乘dt',
            '不复现旧完整trigger/cache，也不宣称修复旧reader/writer/last_ts问题',
            '普通事件/窗口沿Chronaxis有效性和半开观测范围，legacy消息按请求选原帧',
            'RAM为内部保守账本，非RSS或性能测量；未验证平台不作支持承诺'])
    Path(summary['summary_path']).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


def main(argv=None):
    """解析明确选项，运行三模式后只打印短JSON摘要路径。

    参数: argv为可选参数序列，None读取CLI。返回: 完整有限summary dict。
    异常: argparse帮助/参数错误或示例实际原错；不吞取消或伪装成功。
    """
    parser = argparse.ArgumentParser(description='旧INI三模式导入、真实运行与两次发布合成例')
    parser.add_argument('--backend', choices=('reference', 'numpy'), default='numpy')
    parser.add_argument('--batch-rows', type=int, choices=(1, 2, 7), default=2)
    parser.add_argument('--tables', choices=('csv', 'jsonl'), default='jsonl')
    arguments = parser.parse_args(argv)
    summary = run_example(arguments.backend, arguments.batch_rows, arguments.tables)
    print(json.dumps(dict(summary_path=summary['summary_path'], device_label=summary['device_label'],
        backend=summary['backend'], batch_rows=summary['batch_rows'], tables=summary['tables']), ensure_ascii=False))
    return summary


if __name__ == '__main__':
    # 显式入口才生成文件/启动CAN子进程；spawn导入本模块不会再次运行示例。
    main()
