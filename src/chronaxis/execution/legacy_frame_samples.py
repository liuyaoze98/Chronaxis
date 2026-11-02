"""把同次BLF原帧仓与稀疏解码仓按原序连接，供新增报文重建使用。

不重新扫描BLF、不重新解码；新DBC上下文只提供编码布局和复用选择器。
原帧与解码记录的序号、时间和公开帧字段逐项相符，结束时两仓均完整核验。
"""

from ..results.frame_exports import as_export_frame
from ..results.frame_rebuild import FrameSample
from ..results.budget import _reserve_owned_ram,_release_owned_ram,_cleanup_owner
from ..results.errors import ResultClosedError,ResultFormatError


class LegacyFrameSamples:
    """最多保留一条原帧与一条解码记录，拥有两游标而借用原仓和DBC。"""

    def __init__(self,raw_store,message_store,context,budget,*,read_identity,session_id,channel,trace=True):
        """核同次仓身份后开有限游标。参数: 原帧/解码仓/DBC上下文/预算、原scan的read身份/会话/声明通道。返回: owner。异常: 合同/IO错。
        """
        self._budget=budget; self.context=context; self._held_cost=self._fixed_cost=0
        self.channel=channel;self.trace=trace
        self.raw=self.messages=self.pending=None; self._closed=False; self._ended=False
        try:
            context.require_open()
            if raw_store._budget is not budget or raw_store.state!='sealed':
                raise ValueError('重建需要同预算已封口原帧仓')
            if message_store is not None and (message_store._budget is not budget or message_store.state!='sealed'
                    or message_store.source_name!=raw_store.source_name or message_store.session_id!=session_id
                    or message_store.read_identity!=read_identity):
                raise ValueError('原帧与解码仓不是同次读取')
            _reserve_owned_ram(self,262144,'_fixed_cost')
            self.raw=raw_store.iter_frames()
            if message_store is not None:
                self.messages=message_store.iter_records(); self.pending=next(self.messages,None)
        except BaseException as error:
            _cleanup_owner(self,error,'legacy_frame_samples_cleanup_owner','原帧解码连接构造'); raise

    @property
    def closed(self):
        """返回真实关闭状态。参数: 无。返回: bool。异常: 无。
        """
        return self._closed

    def __iter__(self):
        """返回独立游标。参数: 无。返回: self。异常: 无。
        """
        return self

    def __next__(self):
        """连接同原序记录，不跳过完整仓核验。参数: 无。返回: FrameSample。异常: EOF/来源不符/IO错。
        """
        if self._closed or self._ended:
            raise StopIteration
        self.context.require_open()
        try:
            raw=next(self.raw)
        except StopIteration:
            if self.pending is not None or not self.raw.verified_eof or self.messages is not None and not self.messages.verified_eof:
                raise ResultFormatError('原帧和解码仓没有共同完整结束')
            self._ended=True; raise
        decoded=None
        if self.pending is not None:
            item=self.pending
            if item.decoded.sequence<raw.sequence:
                raise ResultFormatError('解码仓出现无对应原帧记录')
            if item.decoded.sequence==raw.sequence:
                if item.time_ns!=raw.time_ns or item.decoded.frame!=raw.frame:
                    raise ResultFormatError('重建原帧与解码记录内容不符')
                decoded=item.decoded; self.pending=next(self.messages,None)
        # 与同次读取使用相同候选选择，不把标准与扩展帧的同数值ID混为一条。
        message=self.context.observe(raw.frame)
        known=raw.frame.channel==self.channel and self.context.is_known_frame(raw.frame)
        values=(); layout=(); valid=True
        rule=next((rule for rule in self.context.rules if rule.matches(raw.frame)),None)
        if rule is not None and not raw.frame.is_error_frame and not raw.frame.is_remote_frame:
            if decoded is None or message is None:
                raise ResultFormatError('已请求重建报文缺同次解码记录')
            values=tuple((name,decoded.values.get(name)) for name in rule.continuous)
            selectors=tuple(signal for signal in message.signals if signal.is_multiplexer)
            # 未激活分支的复用选择器可以缺席；实际布局只包含本次解码已有的选择器。
            layout=tuple((signal.name,int(signal.conversion.numeric_scaled_to_raw(decoded.values[signal.name])))
                for signal in selectors if signal.name in decoded.values)
        return FrameSample(as_export_frame(raw,compact=not self.trace),values,layout,known,valid)

    def close(self):
        """关闭真实两个游标后释放自己的费用。参数: 无。返回: None。异常: 原close错可重试。
        """
        if self._closed:
            return
        for slot in ('raw','messages'):
            owner=getattr(self,slot)
            if owner is not None:
                owner.close(); setattr(self,slot,None)
        self.pending=self.context=None
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost'); self._closed=True
