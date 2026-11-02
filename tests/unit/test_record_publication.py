"""核按需输出摘要、必要复制、文件变化和失败发布恢复；使用已有三格式夹具。"""
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4
import unittest
from unittest.mock import patch
from chronaxis import AnalysisRunner
from chronaxis.results import AnalysisError
from chronaxis.results.artifact_exports import ArtifactExportStore
import test_record_frame_exports as frames


class RecordPublicationTests(unittest.TestCase):
    """同一会话请求信号和原帧；关闭诊断不哈希，开启后摘要与实际文件一致。"""
    setUp=frames.RecordFrameExportTests.setUp
    asc=frames.RecordFrameExportTests.asc
    csv=frames.RecordFrameExportTests.csv
    blf=frames.RecordFrameExportTests.blf
    fixtures=frames.RecordFrameExportTests.fixtures
    plan=frames.RecordFrameExportTests.plan

    def config(self,kind,path,integrity=False,format='csv'):
        """创建同时导出与计算计划。参数: 来源/诊断/表格式。返回: 计划。异常: 原配置错误。"""
        def edit(raw):
            raw['outputs']['tables']=format
            raw['outputs']['signal_csv']={'signals':['current']}
            raw['outputs']['can_frames']={'source':raw['sources'][0]['name'],'format':'asc'}
            raw['diagnostics']={'integrity':integrity}
        return self.plan(kind,path,'fixed',edit)

    def test_default_has_no_export_hashes_or_registration_reads(self):
        """三种原始格式默认不构造摘要；文件只在每次必要复制时读取一次。"""
        for kind,path in self.fixtures().items():
            calls=[];original=ArtifactExportStore._file
            def tracked(owner,source,destination=None,*args,**kwargs):
                calls.append((source,destination));return original(owner,source,destination,*args,**kwargs)
            with ExitStack() as stack:
                for name in ('chronaxis.results.export_files.sha256','chronaxis.results.artifact_exports.sha256'):
                    stack.enter_context(patch(name,side_effect=AssertionError('默认不哈希')))
                stack.enter_context(patch.object(ArtifactExportStore,'_file',tracked))
                with AnalysisRunner().run(self.config(kind,path),self.root/uuid4().hex) as result:
                    self.assertEqual(calls,[])
                    for repeat in range(2):
                        output=self.root/uuid4().hex;result.write(output)
                        records=[json.loads(line) for line in (output/'exports.jsonl').read_text(encoding='utf-8').splitlines()]
                        self.assertEqual(len(calls),4*(repeat+1))
                        self.assertTrue(all(dst is not None for src,dst in calls))
                        self.assertTrue(all('sha256' not in f and '_identity' not in f for r in records for f in r['files']))

    def test_requested_hashes_match_without_table_or_export_rereads(self):
        """CSV/JSONL及两种导出均复用必要写读摘要，不为结果表再扫描；可重复发布。"""
        from chronaxis.results.result import AnalysisResult
        for format in ('csv','jsonl'):
            path=self.fixtures()['can_asc']
            with AnalysisRunner().run(self.config('can_asc',path,True,format),self.root/uuid4().hex) as result:
                with patch.object(AnalysisResult,'_file_info',side_effect=AssertionError('不应重新扫描表')):
                    for repeat in range(2):
                        output=self.root/uuid4().hex;result.write(output)
                        manifest=json.loads((output/'run_manifest.json').read_text(encoding='utf-8'))
                        for info in manifest['outputs']:
                            self.assertEqual(info['sha256'],sha256((output/info['name']).read_bytes()).hexdigest())
                        for record in map(json.loads,(output/'exports.jsonl').read_text(encoding='utf-8').splitlines()):
                            root=output/'exports'/record['directory']
                            for info in record['files']:
                                self.assertEqual(info['sha256'],sha256((root/info['name']).read_bytes()).hexdigest())
                                self.assertNotIn('_identity',info)

    def test_changed_files_fail_and_clean_publication(self):
        """默认拒元数据变化；完整性模式还拒原mtime的同长改值，不能发布成功。"""
        for integrity in (False,True):
            path=self.fixtures()['can_asc']
            with AnalysisRunner().run(self.config('can_asc',path,integrity),self.root/uuid4().hex) as result:
                file=next(result._artifact_exports.path.glob('export-*/original.csv'))
                before=file.stat();data=file.read_bytes();self.assertIn(b'10.0',data)
                file.write_bytes(data.replace(b'10.0',b'19.0'))
                if integrity:os.utime(file,ns=(before.st_atime_ns,before.st_mtime_ns))
                else:
                    # 同长快速写入可能保留mtime；明确构造默认策略可观察的变化。
                    os.utime(file,ns=(before.st_atime_ns,before.st_mtime_ns+1_000_000_000))
                output=self.root/uuid4().hex
                with self.assertRaises(AnalysisError):result.write(output)
                self.assertFalse(output.exists())
                self.assertFalse(list(output.parent.glob('.'+output.name+'.incomplete-*')))
                # 恢复自己的夹具后同一结果可再次发布，不重算输入。
                file.write_bytes(data);os.utime(file,ns=(before.st_atime_ns,before.st_mtime_ns))
                result.write(self.root/uuid4().hex)

    def test_cancel_copy_cleans_and_allows_retry(self):
        """实际复制时取消，关闭当前句柄并清临时目录，再发布能成功，最后预算归零。"""
        path=self.fixtures()['can_asc']
        result=AnalysisRunner().run(self.config('can_asc',path),self.root/uuid4().hex)
        self.addCleanup(result.close);budget=result.spool.budget
        output=self.root/uuid4().hex
        with patch('chronaxis.results.artifact_exports._write_all',side_effect=KeyboardInterrupt('copy cancel')):
            with self.assertRaises(KeyboardInterrupt):result.write(output)
        self.assertFalse(output.exists());self.assertFalse(list(output.parent.glob('.'+output.name+'.incomplete-*')))
        result.write(self.root/uuid4().hex);result.close();self.assertEqual(budget.ram_bytes,0)
