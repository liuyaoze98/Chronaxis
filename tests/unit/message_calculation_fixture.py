"""为消息计算与独立来源核验提供合成输入，不依赖任何退役执行器。

合成原生值覆盖同刻、无效、非有限、布尔和大整数；真实BLF夹具只写work独占目录。
声明路径不充当真实读取证据，调用者负责运行并关闭自己的实际owner。
"""

from configuration_fixtures import current_fixture
import json
from pathlib import Path
from uuid import uuid4
from chronaxis import AnalysisPlan
from chronaxis.legacy.records import LegacyDecodedFrame, LegacyRawFrame, PROFILE_ID


def synthetic_message_plan(root, *, backend, disjunction, constant, unicode_text, batch_rows=2):
    """建立无外部输入依赖的声明。参数: 独占根及语义选项。返回: AnalysisPlan。异常: 原配置校验。"""
    signal = '原始.功率' if unicode_text else 'RawPower'
    message = '报文.功率' if unicode_text else 'Power'
    signals = [] if constant and not disjunction else [dict(name='power', source='bus',
        field=dict(channel=1,  signal=signal, frame_id=256, is_extended=False, is_fd=False),
        dtype='float64', input_unit='W', unit='W', valid_for='1ns', same_time_policy='last_by_sequence')]
    calculations = []
    for index in range(2):
        calculation = dict(name='energy' + str(index), source='bus', profile=PROFILE_ID, operation='legacy_sum',
            message_policy='current_message-v1', update_message=dict(channel=1, frame_id=256,
                is_extended=False, is_fd=False), expr='amount' if constant else 'power * period', unit='J',
            parameters={'amount': dict(value=1.25, unit='J')} if constant else
                       {'period': dict(value=0.25, unit='s')})
        if disjunction:
            calculation['split_by_sign'] = dict(signal='power', bucket='positive' if index == 0 else 'negative',
                                         value_policy='raw_decoded-v1')
        calculations.append(calculation)
    name = '声明输入-中文' if unicode_text else 'declared-input'
    config = dict(config_version=3,
        dataset=dict(name='synthetic_nested', entity='synthetic', session='session',
                     domain=dict(start='0ns', end='100ns')),
        sources=[dict(name='bus', source_type='can_blf', path=str(root / (name + '.blf')),
            legacy_profile=PROFILE_ID, dbc_by_channel={'1': str(root / (name + '.dbc'))},
            time=dict(time_type='relative', unit='s', origin='synthetic_clock', offset='0ns'))],
        signals=signals, derived={}, rules=[], windows=[], calculations=[], message_calculations=calculations,
        execution=dict(backend=backend, batch_rows=batch_rows, result_buffer_rows=7,
                       memory_budget_bytes=256 * 1024**2),
        outputs=dict(tables='jsonl'), metadata=dict(device_label='home', data_kind='synthetic'))
    return AnalysisPlan.from_dict(current_fixture(config), base_dir=root), signal

def synthetic_message_records(signal, *, empty=False):
    """给出手写有限原消息，含同刻和失败诊断。参数: 原字段/空仓选项。返回: tuple。异常: 原模型校验。"""
    if empty:
        return ()
    values = (4.0, -2.0, 0.0, None, float('nan'), float('inf'), -float('inf'), 8.0,
              False, 2**54 + 1, 0.5)
    result = []
    for index, value in enumerate(values):
        # 同刻前两条保独立原yield；稀疏原序不被重编号。未知中文键也必须完整输出。
        time_ns = index // 2
        raw = {} if value is None else {signal: value}
        raw['诊断"\\\n'] = index
        frame = LegacyRawFrame(time_ns * 1e-9, 256, False, False, False, 0,
                               2, bytes((index, 255-index)), False, True, False, False)
        result.append((LegacyDecodedFrame(3 * index + 1, frame, raw), time_ns, bool(index % 2)))
    return tuple(result)

def make_scan_fixture(*, backend='numpy'):
    """写单信号真实BLF和当前计划。参数: backend。返回: 根目录/计划。异常: 原IO或模型错。"""
    import can
    work = Path('work/c12-needed-history-home-20261018/skip-stages') / uuid4().hex
    work.mkdir(parents=True)
    blf, dbc = work / 'input.blf', work / 'input.dbc'
    dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\nBO_ 256 Power: 2 Node\n SG_ Power : 0|16@1+ (1,0) [0|65535] "W" Node\n', encoding='utf-8')
    with can.BLFWriter(blf) as writer:
        for second, frame_id, payload in ((0, 256, b'\xa0\x0f'), (1, 256, b'\xa0\x0f'), (2, 257, b'x')):
            writer.on_message_received(can.Message(timestamp=1700000000.0 + second,
                arbitration_id=frame_id, is_extended_id=False, channel=0, data=payload))
    config = dict(config_version=3,
        dataset=dict(name='legacy_only', entity='synthetic', session='session', domain=dict(start='0s', end='3s')),
        sources=[dict(name='bus', source_type='can_blf', path=str(blf.resolve()), legacy_profile='sclicer-functions-v1',
            dbc_by_channel={'1':str(dbc.resolve())}, time=dict(time_type='relative', unit='s', origin='clock', offset='-1700000000s'))],
        signals=[dict(name='power', source='bus', field=dict(channel=1,  signal='Power',
            frame_id=256, is_extended=False, is_fd=False), dtype='float64', unit='W', valid_for='10s')],
        rules=[], windows=[], calculations=[],
        derived={},
        message_calculations=[dict(name='energy', source='bus', profile='sclicer-functions-v1', operation='legacy_sum',
            message_policy='current_message-v1', update_message=dict(channel=1, frame_id=256, is_extended=False,
                is_fd=False), expr='power * period', unit='J', parameters=dict(period=dict(value=0.1,unit='s')))],
        execution=dict(backend=backend, batch_rows=2, result_buffer_rows=1, memory_budget_bytes=256*1024**2),
        outputs=dict(tables='jsonl'), metadata=dict(device_label='home', data_kind='synthetic'))
    (work/'plan.json').write_text(json.dumps(current_fixture(config),ensure_ascii=False),encoding='utf-8')
    return work, AnalysisPlan.from_dict(current_fixture(config), base_dir=work)

