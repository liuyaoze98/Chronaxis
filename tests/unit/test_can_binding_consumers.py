"""确认自动绑定的下游不会把另一种同ID帧当成缺值或时钟更新。

预期来自两个独立DBC定义：标准帧只有Power，扩展帧只有Other。
仅构造内存投影和消费者，不读写日志；两数值后端共用同一独立预期。
"""

from configuration_fixtures import current_fixture

from types import SimpleNamespace
import unittest

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core.binding import SignalDefinition
from chronaxis.core.types import SignalDType as D
from chronaxis.execution.raw_signal_groups import RawSignalGroups
from chronaxis.execution.current_message_calculation import CurrentMessageCalculation
from chronaxis.legacy.records import LegacyCANField, field_to_dict
from chronaxis.legacy.sum import LegacySkipReason
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources.can_updates import CANUpdateProjection
from test_current_message_calculation import config, update
import test_record_runner as runner_fixtures


class CANBindingConsumerTests(unittest.TestCase):
    """覆盖不属于该帧、确实缺值和纯时钟三种情况，全部资源归零。"""

    def setUp(self):
        """建立两个同ID不同信号的候选事实。参数: 无。返回: None。异常: 构造错误。"""
        self.fields=(LegacyCANField(0,'Power',256),LegacyCANField(0,'Other',256))
        self.facts=tuple({'locator':field_to_dict(field),'dbc_frames':((extended,False),)}
            for field,extended in zip(self.fields,(False,True)))

    def projection(self, *, clock_only=False):
        """返回隔离状态的新投影。参数: clock_only是否只取时钟。返回: 投影。异常: 元数据错误。"""
        # 时钟走生产入口的独立字段参数，不通过伪造解码值替代候选匹配。
        result=CANUpdateProjection('bus','session',() if clock_only else self.fields,
            clock_fields=self.fields if clock_only else (),
            message_keys=((0,256,None,None),) if clock_only else ())
        result.configure_metadata(self.facts)
        return result

    def projected(self, projection, extended, sequence, values):
        """产生与实际帧相符的更新。参数: 投影/帧型/序号/值。返回: 更新。异常: 投影错误。"""
        frame=SimpleNamespace(channel=0,arbitration_id=256,is_extended_id=extended,
            is_fd=False,is_remote_frame=False,is_error_frame=False)
        return projection.build(frame,sequence,values,sequence)

    def test_value_and_clock_groups_ignore_other_frame(self):
        """另一帧不清除旧值或推进时钟；所属帧的None仍产生无效更新。

        参数: 无。返回: None。异常: 断言失败。预期三个输入各只产生其所属信号的一个更新。
        """
        definitions=tuple(SignalDefinition(name,'bus',field.key,D.FLOAT64,'W',1000)
            for name,field in zip(('power','other'),self.fields))
        for backend in ('reference','numpy'):
            for clock_only in ((),('power','other')):
                with self.subTest(backend=backend,clock_only=clock_only):
                    budget=ResourceBudget(); seen=[]; projection=self.projection(clock_only=bool(clock_only))
                    groups=RawSignalGroups(budget,definitions,'session',
                        lambda group:seen.extend((row.name,row.value.valid) for row in group.samples),
                        backend=backend,clock_only=clock_only)
                    try:
                        groups.configure_metadata(self.facts)
                        first=self.projected(projection,False,0,{'Power':4000})
                        second=self.projected(projection,True,1,{'Other':1})
                        third=self.projected(projection,False,2,{})
                        if clock_only:
                            # 纯时钟投影本身不交付任何解码值，仍能识别正确的字段身份。
                            self.assertTrue(all(not row.values for row in (first,second,third)))
                        groups.consume(first);groups.consume(second);groups.consume(third);groups.finish()
                        self.assertEqual([name for name,_ in seen],['power','other','power'])
                        self.assertEqual([valid for _,valid in seen],
                            [False,False,False] if clock_only else [True,True,False])
                    finally:
                        groups.close()
                    self.assertEqual(budget.ram_bytes,0)

    def test_message_calculation_skips_other_identity_but_counts_missing(self):
        """无关扩展帧不计跳过或锁身份；真正缺值None仍计一次缺值。

        参数: 无。返回: None。异常: 断言失败。预期仅两次求值，4000W×0.1s得到400J。
        """
        for backend in ('reference','numpy'):
            raw=config()
            for target in (raw['signals'][0]['field'],raw['message_calculations'][0]['update_message']):
                target.pop('is_extended',None);target.pop('is_fd',None)
            plan=AnalysisPlan.from_dict(current_fixture(raw));budget=ResourceBudget();projection=self.projection()
            owner=CurrentMessageCalculation(plan.message_calculations[0],plan.sources,plan.bindings,
                'session',budget,backend=backend)
            try:
                owner.consume((self.projected(projection,True,0,{'Other':1}),))
                owner.consume((self.projected(projection,False,1,{'Power':4000}),))
                owner.consume((self.projected(projection,False,2,{}),))
                result=owner.snapshot()
                self.assertEqual((result.value,result.evaluation_count,result.contribution_count),(400.,2,1))
                self.assertEqual(result.skip_counts[LegacySkipReason.MISSING_INPUT],1)
            finally:
                owner.close()
            self.assertEqual(budget.ram_bytes,0)

    def test_explicit_selector_preserves_missing_key_contract(self):
        """显式类型的低层更新仍可用缺键表达缺值，不放宽原计算合同。

        参数: 无。返回: None。异常: 断言失败。缺键与显式None都表示一次缺值求值。
        """
        from dataclasses import replace
        plan=AnalysisPlan.from_dict(current_fixture(config()));budget=ResourceBudget()
        owner=CurrentMessageCalculation(plan.message_calculations[0],plan.sources,plan.bindings,
            'session',budget,backend='reference')
        try:
            owner.consume((replace(update(4000.,0,time=0),values={}),))
            self.assertEqual(owner.snapshot().skip_counts[LegacySkipReason.MISSING_INPUT],1)
        finally:
            owner.close()
        self.assertEqual(budget.ram_bytes,0)


class CANBindingClockRunnerTests(unittest.TestCase):
    """真实ASC经来源游标交给时钟消费者，同ID无关帧不得增加固定周期累计。"""

    setUp=runner_fixtures.RecordRunnerTests.setUp
    asc=runner_fixtures.RecordRunnerTests.asc
    csv=runner_fixtures.RecordRunnerTests.csv
    blf=runner_fixtures.RecordRunnerTests.blf
    fixtures=runner_fixtures.RecordRunnerTests.fixtures
    plan=runner_fixtures.RecordRunnerTests.plan

    def test_clock_only_candidate_does_not_decode_or_advance_other_type(self):
        """标准Tick驱动两次0.1s，扩展Other不驱动，4000W累计800J。

        参数: 无。返回: None。异常: 断言或夹具读写失败。
        同次DBC只解码0秒的电压电流消息，不解码Tick或Other。
        """
        from copy import deepcopy
        from uuid import uuid4
        from unittest.mock import patch
        import cantools
        # 两种时钟候选共用数值ID257，只有标准帧含所需Tick；不靠ID大小推断帧型。
        self.fixtures()
        with self.dbc.open('a',encoding='utf-8') as handle:
            handle.write('BO_ 257 Clock: 1 Node\n SG_ Tick : 0|8@1+ (1,0) [0|255] "" Node\n'
                'BO_ 2147483905 OtherClock: 1 Node\n SG_ Other : 0|8@1+ (1,0) [0|255] "" Node\n')
        path=self.asc('0.00 1 100 Rx d 2 C8 0A\n0.00 1 101 Rx d 1 01\n'
            '0.06 1 101x Rx d 1 02\n0.12 1 101 Rx d 1 03\n'
            '0.18 1 101x Rx d 1 04\n0.30 1 101 Rx d 1 05\n').path

        def edit(raw):
            """只将新增Tick用于时钟。参数: 配置。返回: None。异常: 夹具键缺失。"""
            clock=deepcopy(raw['signals'][0]);clock.update(name='clock',unit='1',conversion={'input_unit':'1'})
            clock['field'].update(signal='Tick',frame_id=257)
            clock['field'].pop('is_extended',None);clock['field'].pop('is_fd',None)
            raw['signals'].append(clock);raw['intervals']['default']['driver']='clock'

        # 两后端采用同一手算；观察真实DBC解码调用，防止修复偷偷增加无用解码。
        original=cantools.database.can.message.Message.decode
        for backend in ('reference','numpy'):
            with patch.object(cantools.database.can.message.Message,'decode',autospec=True,side_effect=original) as decode:
                with AnalysisRunner(backend).run(self.plan('can_asc',path,edit=edit),self.root/uuid4().hex) as result:
                    values={row.calculation_id:row.value for row in result.iter_calculations()}
                    self.assertEqual(values['energy'],800.)
                self.assertEqual(decode.call_count,1)
