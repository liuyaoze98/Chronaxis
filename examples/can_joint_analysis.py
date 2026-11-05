"""用合成CAN电压与独立CSV电流联合分析，并两次发布同一原始BLF片段。

运行时只在work/can-joint-example下建立唯一案例目录、三帧BLF、16位DBC、两行CSV
和完整计划。两来源显式共享relative origin；CAN原浮点秒只施加一次声明offset。
350V与2A在0—5秒形成700W，5秒同类空payload使电压缺失，联合观测仍到CSV的8秒。
因此请求0—10秒的已知能量为3500J，请求覆盖0.8、值有效覆盖0.625；事件在5秒中断，
片段[0,5)保0秒电压帧和2秒未知ID帧，排除5秒右端帧。合成真值不代表用户实际日志。

分析仅调用公开load_analysis_plan、AnalysisRunner和AnalysisResult；不实现读取/条件/积分内核。
can依赖只在生成或独立核对小夹具时导入，导入本模块不创建文件或进程。有限结果行
逐条设上限并关闭游标，run完成后向两个新目录write；第二次发布复用已生成工件。
summary.json保设备标签、手算与实际、来源及输出路径；上下文退出关闭结果资源。
"""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

from chronaxis import AnalysisResult, AnalysisRunner, load_analysis_plan


def logical_frames(path, maximum):
    """按原序读取小BLF的完整12字段，供输入与两个发布副本逐帧比较。

    参数: path为本例BLF；maximum是明确帧数上限。返回: 有限逻辑帧字典列表。
    异常: CAN依赖/文件错误或超上限AssertionError传播，finally始终stop真实reader。
    副作用: 独立核对读取不经生产旧链，输入核对发生在AnalysisRunner.run之前。
    """
    import can
    reader = can.BLFReader(path)
    frames = []
    try:
        for frame in reader:
            assert len(frames) < maximum, '合成BLF超出已声明有限帧数'
            # hex保原浮点秒的精确值；载荷用hex只是JSON表示，不改变字节或原序。
            frames.append(dict(timestamp_hex=frame.timestamp.hex(), frame_id=frame.arbitration_id,
                is_extended=frame.is_extended_id, is_remote=frame.is_remote_frame,
                is_error=frame.is_error_frame, channel=frame.channel, dlc=frame.dlc,
                data_hex=bytes(frame.data).hex(), is_fd=frame.is_fd, is_rx=frame.is_rx,
                bitrate_switch=frame.bitrate_switch, error_state_indicator=frame.error_state_indicator))
    finally:
        reader.stop()
    return frames


def create_inputs(root):
    """生成本例独占BLF/DBC/CSV，缺值由真实同类空payload产生而非手造分析行。

    参数: root为新案例根目录。返回: (BLF路径,DBC路径,CSV路径,三帧逻辑真值)。
    异常: 可选CAN依赖或实际写出/关闭错误传播；不skip、不改历史项目或用户输入。
    """
    import can
    blf, dbc, csv = root / 'voltage.blf', root / 'voltage.dbc', root / 'current.csv'
    dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
        'BO_ 256 Frame: 2 Node\n SG_ Voltage : 0|16@1+ (1,0) [0|65535] "V" Node\n',
        encoding='utf-8')
    writer = can.BLFWriter(blf)
    try:
        specifications = ((0, 256, (350).to_bytes(2, 'little'), False),
            (2, 257, b'\xaa', True), (5, 256, b'', False))
        for second, frame_id, payload, extended in specifications:
            writer.on_message_received(can.Message(timestamp=1700000000.0 + second,
                arbitration_id=frame_id, is_extended_id=extended, channel=0, data=payload))
    finally:
        writer.stop()
    csv.write_text('ns,current\n0,2\n8000000000,2\n', encoding='utf-8')
    truth = logical_frames(blf, 3)
    assert len(truth) == 3
    assert [frame['frame_id'] for frame in truth] == [256, 257, 256]
    assert [frame['data_hex'] for frame in truth] == ['5e01', 'aa', '']
    return blf, dbc, csv, truth


def configuration(blf, dbc, csv, backend, batch_rows):
    """建立真实单位、共同origin、原CAN秒offset与有限预算的公开JSON声明。

    参数: blf/dbc/csv为本例输入Path；backend/batch_rows为明确执行选项。
    返回: load_analysis_plan可读取的配置dict。异常: 无I/O，错误选项由main及公开计划校验拒绝。
    """
    origin = 'synthetic_joint_clock'
    return dict(config_version=4,
        dataset=dict(name='joint_example', entity='synthetic_device', session='joint_session',
            domain=dict(start='0s', end='10s')),
        sources=[dict(name='bus', source_type='can_blf', path=str(blf), legacy_profile='sclicer-functions-v1',
            dbc_by_channel={'0': str(dbc)}, reader_options=dict(decode_policy='legacy'),
            time=dict(time_type='relative', unit='s', origin=origin, offset='-1700000000s')),
            dict(name='current_table', source_type='signal_csv', path=str(csv), time_column='ns',
                time=dict(time_type='relative', unit='ns', origin=origin))],
        signals=[dict(name='voltage', source='bus', field=dict(channel=0,
            signal='Voltage', frame_id=256, is_extended=False, is_fd=False),
            dtype='float64', unit='V', valid_for='20s'),
            dict(name='current', source='current_table', field='current', dtype='float64',
                unit='A', valid_for='20s')],
        derived=dict(power=dict(expr='voltage * current', unit='W')),
        rules=[dict(name='active', rule_type='condition_duration', condition='voltage > 300 and current > 0', minimum_duration='0s')],
        windows=[dict(name='activity', rule='active', anchor='activity', pre='0s', post='0s', merge='none')],
        calculations=[dict(name='session_energy', scope='session', operation='integral', expr='power', unit='J'),
            dict(name='event_energy', scope='event:active', operation='integral', expr='power', unit='J'),
            dict(name='segment_energy', scope='segment:activity', operation='integral', expr='power', unit='J'),
            dict(name='voltage_rows', scope='session', operation='select', expr='voltage')],
        execution=dict(backend=backend, batch_rows=batch_rows, result_buffer_rows=1,
            memory_budget_bytes=256 * 1024**2),
        outputs=dict(tables='csv', can_frames=dict(source='bus', format='blf', scope='segments', source_time_reference='epoch')),
        diagnostics=dict(integrity=True, trace=True),
        # AnalysisRunner读取计划metadata；由示例显式传入已核环境标签，不假定框架自动识别设备。
        metadata=dict(device_label=os.environ.get('CHRONAXIS_DEVICE_LABEL', 'pending'),
            data_kind='synthetic', example='can_joint_analysis'))


def bounded_rows(result, table, maximum):
    """耗尽一个已明确行数上限的公开结果游标，并在任何退出路径关闭它。

    参数: result为本次AnalysisResult；table为events/segments/calculations；maximum为上限。
    返回: 有限typed行列表。异常: 实际结果读取错误或超上限AssertionError传播。
    """
    reader = getattr(result, 'iter_' + table)()
    rows = []
    try:
        for row in reader:
            assert len(rows) < maximum, '合成结果超出已声明有限行数'
            rows.append(row)
    finally:
        reader.close()
    return rows


def quality_names(quality):
    """从结果自带的typed质量枚举读取名称，避免自行定义或猜测数值位。

    参数: quality为实际结果质量。返回: 已包含标志的名称列表，NONE返回空列表。
    异常: 非既有typed质量会自然失败，不从文本或自由整数伪造质量。
    """
    return [flag.name for flag in quality]


def calculation_facts(row):
    """读取当前标量事实。参数: 平坦计算行。返回: 数值、状态及质量。异常: 字段错误。"""
    return dict(value=row.value, unit=row.unit, status=row.status, reason=row.reason,
                quality=quality_names(row.quality))


def published_raw(manifest, expected_frames):
    """从公开发布目录核单条索引、BLF实际SHA和完整12字段，不调用原读写封装。

    参数: manifest为本次write返回值；expected_frames为输入前两帧有限真值。
    返回: 本次发布路径、原始文件名和实际SHA的有限dict。
    异常: 索引多行、完成状态、数量、SHA或帧字段不符时AssertionError；实际I/O错传播。
    """
    assert manifest.status == 'completed'
    folder = manifest.output_dir
    facts = json.loads(manifest.manifest_path.read_text(encoding='utf-8'))
    assert facts['status'] == 'completed'
    index_path = folder / 'exports.jsonl'
    assert index_path in manifest.output_files
    with index_path.open(encoding='utf-8') as handle:
        record = json.loads(handle.readline())
        assert handle.readline() == ''
    assert record['export_type'] == 'can_frames' and record['scope'] == 'segments'
    assert record['interval'] == [0, 5_000_000_000]
    directory = folder / 'exports' / record['directory']
    metadata = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    assert metadata['frames'] == 2 and metadata['source'] == 'bus'
    path = directory / 'frames.blf'
    payload = path.read_bytes()
    digest = sha256(payload).hexdigest()
    file_fact = next(item for item in record['files'] if item['name'] == 'frames.blf')
    assert len(payload) == file_fact['bytes'] and digest == file_fact['sha256']
    assert logical_frames(path, 2) == expected_frames
    return dict(output_dir=str(folder), manifest_path=str(manifest.manifest_path),
        raw_index=str(index_path), raw_file=str(path), raw_sha256=digest, raw_frame_count=2)


def main(backend='numpy', batch_rows=2):
    """生成有限联合案例，核手算与缺值边界，两次发布后返回并保存摘要。

    参数: backend为numpy/reference；batch_rows为正原生int，默认2。
    返回: summary dict，含summary_path及所有输入/输出绝对路径；结果已退出上下文关闭。
    异常: 类型/选项错误、真实公开分析/发布错误或手算断言失败原样传播。
    副作用: 仅在work/can-joint-example/<uuid>写合成输入、暂存、两份发布及summary.json。
    """
    if type(backend) is not str or backend not in ('numpy', 'reference'):
        raise ValueError('backend必须为numpy或reference')
    if type(batch_rows) is not int or batch_rows <= 0:
        raise ValueError('batch_rows必须为正原生int')
    ns = 1_000_000_000
    root = Path(__file__).resolve().parents[1] / 'work/can-joint-example' / uuid4().hex
    root.mkdir(parents=True)
    blf, dbc, csv, truth = create_inputs(root)
    plan_path = root / 'analysis.json'
    plan_path.write_text(json.dumps(configuration(blf, dbc, csv, backend, batch_rows),
        ensure_ascii=False, indent=2), encoding='utf-8')
    plan = load_analysis_plan(plan_path)
    runner = AnalysisRunner()
    report = runner.explain(plan)
    assert report.validation.execution_ready and not report.validation.errors
    with runner.run(plan, work_dir=root / 'analysis-work') as result:
        assert isinstance(result, AnalysisResult)
        events, segments = bounded_rows(result, 'events', 1), bounded_rows(result, 'segments', 1)
        assert len(events) == len(segments) == 1
        event, segment = events[0], segments[0]
        assert (event.start_ns, event.end_ns, event.status) == (0, 5*ns, 'interrupted')
        assert (segment.start_ns, segment.end_ns) == (0, 5*ns)
        assert segment.parent_event_ids == (event.event_id,)
        rows = bounded_rows(result, 'calculations', 3)
        selected = bounded_rows(result, 'selections', 2)
        scalar = {row.calculation_id: row for row in rows}
        assert len(rows) == 3 and len(selected) == 2
        assert set(scalar) == {'session_energy', 'event_energy', 'segment_energy'}
        actual_calculations = {name: calculation_facts(row) for name, row in scalar.items()}
        for name, facts in actual_calculations.items():
            assert facts['value'] == 3500.0 and facts['unit'] == 'J'
            assert facts['status'] == ('partial' if name == 'session_energy' else 'complete')
        assert [(row.time_ns, row.value, row.valid) for row in selected] == [(0, 350.0, True), (5*ns, None, False)]
        missing_names = quality_names(selected[1].quality)
        assert 'MISSING' in missing_names and 'DECODE_ERROR' not in missing_names
        diagnostics = {item.source: item for item in result.metadata.input_diagnostics}
        can_fact = diagnostics['bus']
        assert can_fact.record_count == 2 and can_fact.source_eof
        assert dict(can_fact.bindings)['voltage']
        traces = bounded_rows(result, 'input_trace', 8)
        assert {row.source for row in traces} == {'bus', 'current_table'}
        row_counts = result.run_manifest['row_counts']
        assert row_counts == dict(events=1, segments=1, calculations=3, selections=2, input_trace=len(traces))
        # 两次write都在同一个已返回结果上执行，输入真值核对发生在run之前。
        outputs = [published_raw(result.write(root / 'published-1'), truth[:2]),
            published_raw(result.write(root / 'published-2'), truth[:2])]
        assert outputs[0]['raw_sha256'] == outputs[1]['raw_sha256']
        # 沿实际运行清单记录设备；环境未确认时保pending，不因示例最初在家中编写就猜home。
        summary = dict(device_label=result.metadata.device_label, data_kind='synthetic', backend=backend, batch_rows=batch_rows,
            work_root=str(root), plan_path=str(plan_path), summary_path=str(root / 'summary.json'),
            sources=dict(can_blf=str(blf), dbc=str(dbc), current_csv=str(csv),
                shared_origin='synthetic_joint_clock', can_offset_ns=-1700000000 * ns,
                required_can_record_count=can_fact.record_count, input_logical_frames=truth),
            manual=dict(requested_ns=[0, 10 * ns], joint_actual_ns=[0, 8 * ns],
                known_power_W=700.0, known_power_ns=[0, 5 * ns], energy_J=3500.0,
                requested_coverage=0.8, value_coverage=0.625, raw_input_indices=[0, 1]),
            actual=dict(calculations=actual_calculations, rule=dict(start_ns=event.start_ns, end_ns=event.end_ns,
                status=event.status), segment=dict(actual_ns=[segment.start_ns, segment.end_ns],
                status=segment.status), voltage_rows=[dict(time_ns=row.time_ns, value=row.value,
                valid=row.valid, quality=quality_names(row.quality)) for row in selected]),
            counts=row_counts, outputs=outputs)
    # 只有结果上下文成功关闭才生成成功摘要；失败保留原案例目录供定位。
    Path(summary['summary_path']).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"{backend}/batch={batch_rows}: 3500 J；会话partial；原始片段2帧；{summary['summary_path']}")
    return summary


if __name__ == '__main__':
    # spawn子进程导入主模块时不再次生成输入或运行分析。
    parser = argparse.ArgumentParser(description='合成CAN电压与CSV电流联合分析和BLF片段示例')
    parser.add_argument('--backend', choices=('numpy', 'reference'), default='numpy')
    parser.add_argument('--batch-rows', type=int, default=2)
    arguments = parser.parse_args()
    main(arguments.backend, arguments.batch_rows)
