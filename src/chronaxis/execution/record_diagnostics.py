"""仅在请求追溯或完整性诊断时观察同次输入，不增加来源扫描。

trace逐条保存所需输入值和来源序号；integrity随这些记录计算摘要，两者独立。
来源配置只在清单保存一次。借入值在调用结束释放，固定哈希状态按来源付费；
最终明细使用已有结果仓的有界外排和生命周期，不建立第二份历史。
"""
import hashlib
import json
from math import isfinite
from ..results.input_diagnostics import InputDiagnostic
from ..results.budget import _reserve_owned_ram,_release_owned_ram,_cleanup_owner
from ..results.errors import ResultClosedError
from .history import _metadata_bytes


class RecordDiagnostics:
    """保存每来源一个计数及可选摘要；逐条明细同步交给最终结果消费者。"""
    def __init__(self,plan,requirements,budget,consumer):
        """预约实际来源状态。参数: 计划/需求/预算/追溯回调。返回: owner。异常: 预算错误。"""
        self._plan,self._requirements,self._budget=plan,requirements,budget
        self._consumer=consumer if plan.diagnostics.trace else None
        self._held_cost=self._fixed_cost=self._row_cost=0
        self._counts=self._hashes=None
        self._closed=False
        try:
            names=tuple(s.source for s in requirements.sources if s.active)
            _reserve_owned_ram(self,65536+4096*len(names),'_fixed_cost')
            # 来源清单只计路径/需求，不遍历memory来源的全部数据；覆盖最终清单交接副本。
            extra=32*_metadata_bytes(requirements)
            for source in plan.sources:
                if source.name not in names:continue
                config=source.config
                paths=(config.input_paths if source.source_type=='can_blf' else
                    (item.path for item in config.inputs) if source.source_type in ('can_asc','asc_or_blf','raw_can_csv') else
                    config.paths if source.source_type=='signal_csv' else ())
                extra+=sum(4096+256*len(str(path)) for path in paths)
            _reserve_owned_ram(self,extra,'_fixed_cost')
            self._counts=dict.fromkeys(names,0)
            self._hashes={name:hashlib.sha256() for name in names} if plan.diagnostics.integrity else {}
        except BaseException as error:
            _cleanup_owner(self,error,'record_diagnostics_cleanup_owner','输入诊断');raise

    def consume(self,source,sequence,time_ns,record_type,locator,values,quality):
        """借入必要输入，按请求追溯/取摘要。参数: 定位/类型/值/质量。返回: None。异常: 编码/预算/取消。"""
        if self._closed:raise ResultClosedError('输入诊断已关闭')
        payload=normalized=text=None
        try:
            # 先覆盖编码及非有限标签空间，非法值不偷偷转成有效0。
            _reserve_owned_ram(self,16384+64*_metadata_bytes(values),'_row_cost')
            normalized={name:({'nonfinite':'nan' if value!=value else 'inf' if value>0 else '-inf'}
                if type(value) is float and not isfinite(value) else value) for name,value in values.items()}
            text=json.dumps(normalized,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':'))
            if source in self._hashes:
                payload=json.dumps((sequence,time_ns,record_type,locator,int(quality),text),ensure_ascii=False,
                    allow_nan=False,separators=(',',':')).encode('utf-8')
                self._hashes[source].update(len(payload).to_bytes(8,'big'))
                self._hashes[source].update(payload)
            if self._consumer is not None:
                self._consumer(source,sequence,time_ns,record_type,locator,text,quality)
            self._counts[source]+=1
        finally:
            payload=normalized=values=text=None
            _release_owned_ram(self,self._row_cost,'_row_cost')

    def summaries(self,cursors):
        """仅EOF后交付有限来源清单。参数: 实际游标。返回: InputDiagnostic tuple。异常: 不完整来源。"""
        result=[]
        for cursor in cursors:
            source=next(s for s in self._plan.sources if s.name==cursor.source_name)
            config=source.config
            paths=(tuple(str(p) for p in config.input_paths) if source.source_type=='can_blf' else
                tuple(str(i.path) for i in config.inputs) if source.source_type in ('can_asc','asc_or_blf','raw_can_csv') else
                tuple(str(path) for path in config.paths) if source.source_type=='signal_csv' else ())
            req=self._requirements.for_source(source.name)
            result.append(InputDiagnostic(source.name,source.source_type,paths,req.required_aliases,
                tuple((name,self._plan.bindings.resolve(name).field) for name in req.required_aliases),
                req.input_check,req.time_scope,self._counts[source.name],cursor._finished,
                self._hashes[source.name].hexdigest() if source.name in self._hashes else None))
        return tuple(result)

    def close(self):
        """断开哈希/回调后归还本owner费用。参数: 无。返回: None。异常: 预算释放错误。"""
        if self._closed:return
        self._counts=self._hashes=self._consumer=None
        _release_owned_ram(self,self._row_cost,'_row_cost')
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost')
        self._closed=True
