"""核对旧start_end的显式业务选择、字段定位和完整CLI迁移。

使用已标记的合成INI与真实新AnalysisRunner，验证新开始/结束/超时含义及原配置保留。
不运行旧缺陷入口，不宣称与旧准备/确认切片逐帧等价；产物写专用work目录。
"""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from uuid import uuid4
from chronaxis import AnalysisRunner
from chronaxis.migration import import_legacy_ini
from test_start_end_runner import start_end_config

ROOT=Path(__file__).absolute().parents[2]


def mapping_fixture():
    """提供显式新语义及已有合成输入。参数: 无。返回: dict。异常: 无。"""
    analysis=start_end_config();analysis.pop('rules');analysis.pop('windows')
    return _current_mapping(dict(mapping_version=1,path_base='mapping_directory',io_policy='explicit_mapping',analysis=analysis,
        aliases=dict(Start_Flag='begin',End_Flag='done'),
        sections=dict(TRIGGER_test=dict(name='cycle',window='window',semantics='start_end_timeout-v1',emit_initial=True))))


def ini_fixture(duration='0.000000005'):
    """给出5ns时限、0前置与旧未使用post。参数: duration或None。返回: bytes。异常: 编码错误。"""
    text='[TRIGGER_test]\nmode=start_end\nstart_expr=Start_Flag > 0\nend_expr=End_Flag > 0\npre_sec=0\npost_sec=9\n'
    if duration is not None:
        text+='duration_sec='+duration+'\n'
    return text.encode()


class LegacyImportStartEndTests(unittest.TestCase):
    """检查显式迁移，不允许成功报告隐藏业务改变或部分失败。"""

    def convert(self,content=None,mapping=None):
        """调用真实字节入口。参数: 可选原文/映射。返回: 导入结果。异常: 原API错误。"""
        return import_legacy_ini(ini_fixture() if content is None else content,
            mapping_fixture() if mapping is None else mapping,mode='sclicer_start_end',base_dir=ROOT,device_label='home')

    def test_explicit_semantics_and_field_mapping(self):
        """明确选择新含义，原post不附加，原文不变化。参数: 无。返回: None。异常: 断言失败。"""
        content=ini_fixture();mapping=mapping_fixture();before=copy.deepcopy(mapping)
        result=self.convert(content,mapping)
        self.assertIsNotNone(result.plan,result.report.to_dict())
        self.assertIs(result.original_ini,content);self.assertEqual(mapping,before)
        self.assertEqual(result.plan.rules[0].start_end.timeout_ns,5)
        self.assertEqual(result.plan.windows[0].post_ns,0)
        self.assertEqual(result.plan.rules[0].dependencies,('begin','done'))
        fields={item.path:item for item in result.report.fields}
        self.assertEqual(fields['[TRIGGER_test].end_expr'].target,'$.rules[0].end_condition')
        self.assertEqual(fields['[TRIGGER_test].post_sec'].status,'replaced')
        self.assertIn('start_end_semantic_change',{item.code for item in result.report.issues})
        self.assertTrue(all(item.status in ('mapped','replaced') for item in result.report.fields))

    def test_both_backends_actual_new_meaning(self):
        """同计划真实运行0–2正常、4–9超时、11–14正常。参数: 无。返回: None。异常: 断言失败。"""
        plan=self.convert().plan;self.assertIsNotNone(plan)
        for backend in ('reference','numpy'):
            result=AnalysisRunner(backend).run(plan,work_dir=ROOT/'work/m3-migrate-home-20261022/import'/uuid4().hex)
            try:
                self.assertEqual([(r.start_ns,r.end_ns,r.status) for r in result.iter_events()],
                                 [(0,2,'closed'),(4,9,'timeout'),(11,14,'closed')])
                self.assertEqual(sorted(r.value for r in result.iter_calculations()),[10,10,52,52,110,110])
            finally:
                result.close()

    def test_unlimited_old_defaults_are_explicit(self):
        """旧非正值及缺省-1映射为null，正5秒保持单位。参数: 无。返回: None。异常: 断言失败。"""
        for duration in (None,'0','-1','-2.5'):
            result=self.convert(ini_fixture(duration))
            self.assertIsNotNone(result.plan,result.report.to_dict())
            self.assertIsNone(result.plan.rules[0].start_end.timeout_ns)
        self.assertEqual(self.convert(ini_fixture('5')).plan.rules[0].start_end.timeout_ns,5*10**9)

    def test_reject_unconfirmed_semantics_and_bad_fields(self):
        """不明确声明新含义则整体拒绝，不猜初始化。参数: 无。返回: None。异常: 断言失败。"""
        for key,value,code in (('semantics','legacy','unconfirmed_start_end_semantics'),
                               ('emit_initial',1,'invalid_start_end_initial')):
            mapping=mapping_fixture();mapping['sections']['TRIGGER_test'][key]=value
            result=self.convert(mapping=mapping)
            self.assertIsNone(result.plan);self.assertEqual(result.report.issues[-1].code,code)
        mapping=mapping_fixture();del mapping['sections']['TRIGGER_test']['semantics']
        self.assertEqual(self.convert(mapping=mapping).report.issues[-1].code,'invalid_section_mapping')
        for duration in ('NaN','inf','0.0000000001','999999999999'):
            result=self.convert(ini_fixture(duration));self.assertIsNone(result.plan)
            issue=result.report.issues[-1];self.assertEqual((issue.code,issue.line),('invalid_duration',7))

    def test_missing_end_and_mixed_file_no_partial_success(self):
        """定位缺字段及混合模式，前段成功不导致部分发布。参数: 无。返回: None。异常: 断言失败。"""
        result=self.convert(ini_fixture().replace(b'end_expr=End_Flag > 0\n',b''))
        self.assertIsNone(result.plan);self.assertEqual(result.report.issues[-1].code,'missing_option')
        mapping=mapping_fixture();mapping['sections']['TRIGGER_other']=dict(mapping['sections']['TRIGGER_test'],name='other',window='other_window')
        result=self.convert(ini_fixture()+b'\n[TRIGGER_other]\nmode=single\nexpr=Start_Flag > 0\n',mapping)
        self.assertIsNone(result.plan);self.assertEqual(result.report.issues[-1].code,'unsupported_mode')

    def test_cli_import_validate_run_and_original(self):
        """真实CLI保原文和差异报告，生成结果含timeout。参数: 无。返回: None。异常: 文件/进程/断言错误。"""
        work=ROOT/'work/m3-migrate-home-20261022/import-cli'/uuid4().hex;work.mkdir(parents=True)
        ini,mapping,plan=work/'original.ini',work/'mapping.json',work/'plan.json'
        ini.write_bytes(ini_fixture());mapping.write_text(json.dumps(mapping_fixture()),encoding='utf-8')
        commands=[['legacy','import',str(ini),'--mode','sclicer_start_end','--mapping',str(mapping),'--output',str(plan)],
                  ['validate',str(plan)],['run',str(plan),'--output',str(work/'result'),'--work-dir',str(work/'run'),'--backend','reference']]
        for index,args in enumerate(commands):
            result=subprocess.run([sys.executable,'-B','-m','chronaxis',*args],cwd=ROOT,
                env=dict(os.environ,CHRONAXIS_DEVICE_LABEL='home',PYTHONDONTWRITEBYTECODE='1'),
                capture_output=True,text=True,encoding='utf-8',timeout=60)
            (work/f'command-{index}.json').write_text(json.dumps(dict(device_label='home',returncode=result.returncode,
                stdout=result.stdout,stderr=result.stderr),ensure_ascii=False),encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertEqual((work/'plan.original.ini').read_bytes(),ini.read_bytes())
        report=json.loads((work/'plan.migration-report.json').read_text(encoding='utf-8'))
        self.assertTrue(any(x['code']=='start_end_semantic_change' for x in report['issues']))
        self.assertIn('超时结束',(work/'result/事件结果.csv').read_text(encoding='utf-8'))


def _current_mapping(mapping):
    """把共享旧夹具声明转换为当前公开结构；不改变原INI、数值或业务断言。"""
    from chronaxis.planning.config_groups import public_configuration
    mapping['analysis']=public_configuration(mapping['analysis'])
    return mapping
