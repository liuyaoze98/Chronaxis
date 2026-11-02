"""以真实CSV和公开入口核对手册的换算、缺失和返回值说明。

合成输入保存在项目work目录；不读取真实日志，不以文档文字代替运行证据。
"""

from configuration_fixtures import current_fixture
from dataclasses import replace
from pathlib import Path
from threading import Event
from uuid import uuid4
import unittest

from chronaxis import AnalysisPlan, AnalysisRunner, PlanValidationError
from chronaxis.batch import BatchJob, BatchPlan, run_batch
from test_start_end_runner import start_end_config


class ManualRuntimeContractTests(unittest.TestCase):
    """每次使用独立目录；成功结果关闭，失败保留真实异常链。"""

    def setUp(self):
        """参数: 无。返回: None。异常: 创建工作目录失败传播。"""
        self.root=Path(__file__).resolve().parents[2]/'work/manual-contract'/uuid4().hex
        self.root.mkdir(parents=True)

    def config(self, first='65535.0', **signal_options):
        """参数: 首个CSV值和信号选项。返回: 两秒积分配置。异常: 写入错误传播。"""
        # 解析后的整数65535与浮点哨兵65535.0在Python数值比较之外还要比较类型。
        path=self.root/(uuid4().hex+'.csv')
        path.write_text('t,p\n0,'+first+'\n1,1\n2,1\n',encoding='utf8')
        return dict(config_version=3,dataset=dict(name='demo',entity='device',session='session',domain=dict(start='0s',end='2s')),
            sources=[dict(name='table',source_type='signal_csv',path=str(path),time_column='t',time=dict(time_type='relative',unit='s',origin='clock'))],
            signals=[dict(name='power',source='table',field='p',dtype='float64',unit='W',valid_for='3s',**signal_options)],
            calculations=[dict(name='energy',scope='session',operation='integral',expr='power')])

    def run_result(self, raw):
        """参数: 配置字典。返回: 真实结果。异常: 计划或运行错误；成功结果登记关闭。"""
        result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),work_dir=self.root/uuid4().hex)
        self.addCleanup(result.close)
        return result

    def test_sentinel_matches_parsed_native_type(self):
        """参数: 无。返回: None。异常: 类型匹配或手算积分不一致断言失败。"""
        for sentinel,expected,status in ((65535.0,65536.0,'complete'),(65535,1.0,'partial')):
            row=next(self.run_result(self.config(invalid_values=[sentinel])).iter_calculations())
            self.assertEqual((row.value,row.status),(expected,status))

    def test_missing_range_and_parse_failure_differ(self):
        """参数: 无。返回: None。异常: 缺失/越界未继续或坏文本未报错时失败。"""
        missing=self.config('NA');missing['sources'][0]['missing_values']=['NA']
        for raw in (missing,self.config(valid_range=[0,10])):
            row=next(self.run_result(raw).iter_calculations())
            self.assertEqual((row.value,row.status),(1.0,'partial'))
        with self.assertRaises(Exception) as caught:self.run_result(self.config('bad'))
        chain=[];error=caught.exception
        while error is not None:
            chain.append(type(error).__name__);error=error.__cause__
        self.assertEqual(chain,['AnalysisError','SourceReadError','ValueError','InvalidOperation'])

    def test_known_unit_conversion_and_semantic_dependency(self):
        """参数: 无。返回: None。异常: 已知单位约束或语义依赖发生变化时失败。"""
        raw=self.config('5000',input_unit='mA',scale=0.001);raw['signals'][0]['unit']='A'
        self.assertAlmostEqual(next(self.run_result(raw).iter_calculations()).value,5.001)
        for changes in ({'scale':2},{'scale':-1},{'offset':-2},{'semantic_contract_version':'1'}):
            with self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(current_fixture(self.config(**changes)))

    def test_preset_period_and_metadata_detail(self):
        """参数: 无。返回: None。异常: 默认有效期或摘要/详细返回不符时失败。"""
        raw=self.config('10');signal=raw['signals'][0];signal.pop('valid_for');signal['period']='1s'
        raw['presets']=[dict(name='high',preset_type='threshold_excursion',version='1',role_bindings={'signal':'power'},parameters=dict(unit='W',enter_threshold=8,exit_threshold=5))]
        result=self.run_result(raw)
        # 当前运行入口生成摘要；另用同一计划定义构造非空模型，独立核对序列化分支。
        metadata=replace(result.metadata,signal_bindings=AnalysisPlan.from_dict(current_fixture(raw)).bindings.signals)
        self.assertTrue(metadata.signal_bindings)
        self.assertEqual(metadata.signal_bindings[0].valid_for_ns,3_000_000_000)
        self.assertNotIn('signal_bindings',replace(metadata,detailed_diagnostics=False).to_dict())
        self.assertTrue(replace(metadata,detailed_diagnostics=True).to_dict()['signal_bindings'])

    def test_batch_null_fields_and_not_started(self):
        """参数: 无。返回: None。异常: 正常、加载失败和取消字段不一致时失败。"""
        # 正常内存计划没有plan_path，不等于任务失败；失败任务也不等于批次基础设施错误。
        plan=AnalysisPlan.from_dict(current_fixture(start_end_config()))
        report=run_batch(BatchPlan((BatchJob('ok',plan),BatchJob('bad',self.root/'missing.yaml'))),self.root/'batch',device_label='home')
        ok,bad=report.jobs
        self.assertEqual(ok.status,'completed');self.assertIsNone(ok.plan_path);self.assertIsNone(ok.error_type)
        self.assertEqual(bad.status,'failed');self.assertIsNone(bad.run_id);self.assertIsNone(bad.plan_identity)
        self.assertIsNone(report.infrastructure_error);self.assertEqual(report.status,'failed')
        cancel=Event();cancel.set()
        job=run_batch(BatchPlan((BatchJob('cancel',plan),)),self.root/'cancel',cancel_event=cancel,device_label='home').jobs[0]
        self.assertEqual((job.status,job.error_type),('cancelled','not_started'))
        self.assertNotIn('diagnostics',job.to_dict())


if __name__=='__main__':unittest.main()
