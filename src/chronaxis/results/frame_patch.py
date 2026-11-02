"""用已有DBC位域工具更新明确的连续信号，其他位沿用同一基础帧。

调用者传入本次已加载的cantools Message及本次已解码的物理值，不再次读取DBC
或解码原帧。整数按nearest_even-v1量化，浮点沿DBC编码后核实际表示误差。
码值或物理值越界立即拒绝。只更新选中位的掩码，计数、校验及未知位保持；
这些生成帧不承诺校验码有效或可用于车辆回放。
"""

from dataclasses import dataclass, replace
from fractions import Fraction
from math import isfinite

from .budget import _reserve_owned_ram, _release_owned_ram, _cleanup_owner
from ..legacy.records import normalize_frame_id


@dataclass(frozen=True)
class FrameRebuildRule:
    """明确报文身份、连续字段及禁止插值的字段；声明不能从名字猜业务含义。"""

    channel: int
    frame_id: int
    continuous: tuple[str,...]
    is_extended: bool | None = None  # 省略时按实际帧与DBC确定，不等同标准帧。
    is_fd: bool | None = None  # 省略时保留输入帧的实际CAN/FD类型。
    protected: tuple[str,...] = ()
    same_time_policy: str = 'error'

    def __post_init__(self):
        """核身份和字段分类。参数: 无。返回: None。异常: 非法/重复/保护字段冲突。
        """
        # ID只在规则建立时归一化，避免每个输出帧重新解释进制。
        object.__setattr__(self,'frame_id',normalize_frame_id(self.frame_id))
        if (type(self.channel) is not int or self.channel<0
                or self.is_extended is False and self.frame_id>0x7ff
                or self.is_extended is not None and type(self.is_extended) is not bool
                or self.is_fd is not None and type(self.is_fd) is not bool
                or self.same_time_policy not in ('error','last_by_sequence')):
            raise ValueError('报文重建身份或同刻策略非法')
        for names in (self.continuous,self.protected):
            if type(names) is not tuple or len(names)>4096 or any(type(n) is not str or not n for n in names) or len(set(names))!=len(names):
                raise ValueError('报文重建字段需要唯一非空名称tuple')
        if not self.continuous or set(self.continuous)&set(self.protected):
            raise ValueError('必须选择连续量，且不能插值保护的计数或校验字段')

    def matches(self,frame):
        """按实际帧身份匹配。参数: frame原帧。返回: bool。异常: 原模型访问错。
        """
        return (frame.channel==self.channel and frame.arbitration_id==self.frame_id
            and (self.is_extended is None or frame.is_extended_id==self.is_extended)
            and (self.is_fd is None or frame.is_fd==self.is_fd))


class DBCFramePatch:
    """借用一条已加载DBC定义，拥有选中位格式与预算；只缓存当前复用布局。"""

    def __init__(self,rule,message,budget):
        """核DBC身份与连续字段并预约格式空间。参数: rule/message/budget。返回: patcher。异常: 不匹配或预算错。
        """
        if type(rule) is not FrameRebuildRule:
            raise TypeError('需要FrameRebuildRule')
        self.rule=rule; self.message=message; self._budget=budget
        self._held_cost=self._fixed_cost=0; self._closed=False
        self.signals={}; self.formats=None; self.active=(); self.mask=0
        self._identity=None
        try:
            _reserve_owned_ram(self,262144+len(message.signals)*16384,'_fixed_cost')
            if (message.frame_id!=rule.frame_id
                    or rule.is_extended is not None and message.is_extended_frame!=rule.is_extended
                    or rule.is_fd is True and not message.is_fd
                    or not 0<message.length<=64 or message.is_container):
                raise ValueError('重建规则与DBC报文身份/载荷不符或为容器报文')
            self.signals={signal.name:signal for signal in message.signals}
            for name in (*rule.continuous,*rule.protected):
                if name not in self.signals:
                    raise ValueError('DBC缺少重建声明字段: '+name)
            for name in rule.continuous:
                signal=self.signals[name]
                if signal.is_multiplexer or signal.choices or not signal.scale or signal.length==1:
                    raise ValueError('复用选择器、枚举/布尔或零倍率不能当连续量: '+name)
        except BaseException as error:
            _cleanup_owner(self,error,'frame_patch_cleanup_owner','DBC位域重建构造')
            raise

    def accept_frame(self,frame):
        """检查实际基础帧与选定DBC，并识别自动规则后续出现的帧型冲突。

        参数: frame为同次输入原帧。返回: None。异常: ValueError为类型不匹配或歧义。
        副作用: 只记录首次匹配的两个类型标志，后续同型帧不扩大状态。
        """
        if (not self.rule.matches(frame) or frame.is_extended_id!=self.message.is_extended_frame
                or frame.is_fd and not self.message.is_fd):
            raise ValueError('重建实际帧与已选DBC类型不符')
        identity=(frame.is_extended_id,frame.is_fd)
        if self._identity is not None and self._identity!=identity:
            flag='is_extended' if self._identity[0]!=identity[0] else 'is_fd'
            raise ValueError('重建规则匹配多种实际帧类型，请补充'+flag)
        self._identity=identity

    def selected(self,layout):
        """只取当前复用分支适用的连续字段。参数: layout原生选择器码值tuple。返回: 名称tuple。异常: 布局非法。
        """
        selectors=dict(layout)
        if len(selectors)!=len(layout) or any(name not in self.signals or not self.signals[name].is_multiplexer
                or type(value) is not int for name,value in layout):
            raise ValueError('报文复用布局不合法')
        selected=[]
        for name in self.rule.continuous:
            signal=self.signals[name]; visited=set(); applicable=True
            # 沿真实父选择器判断，避免将另一分支同位置的位当作本连续量。
            while signal.multiplexer_signal is not None:
                parent=signal.multiplexer_signal
                if parent in visited or parent not in self.signals:
                    raise ValueError('DBC复用父链非法')
                visited.add(parent)
                if parent not in selectors or selectors[parent] not in signal.multiplexer_ids:
                    applicable=False; break
                signal=self.signals[parent]
            if applicable:
                selected.append(name)
        return tuple(selected)

    def patch(self,base,values,layout,*,exact_values=None,trace=True):
        """仅按允许掩码更新载荷并记录量化误差。

        参数: base同一基础LegacyRawFrame；values所需物理估计dict；layout实际复用布局；
            exact_values可选的有理数编码目标，用于避免中间float改变半码决策。
        返回: (新帧, 每字段目标/码值/实际值/误差tuple)。异常: 缺值、范围/格式/编码错误。
        """
        if self._closed or not self.rule.matches(base) or base.dlc!=self.message.length or len(base.data)!=self.message.length:
            raise ValueError('重建基础帧已关闭、身份或长度不符')
        self.accept_frame(base)
        selected=self.selected(layout)
        if not selected or set(values)!=set(selected):
            raise ValueError('当前复用布局缺少必须的连续值')
        if exact_values is not None and (set(exact_values)!=set(selected) or any(type(v) is not Fraction for v in exact_values.values())):
            raise ValueError('精确量化目标需要同组Fraction字段')
        from cantools.database.utils import create_encode_decode_formats,encode_data,decode_data
        if selected!=self.active:
            # 编解码格式来自现有库；仅所选信号的非padding位允许改变。
            self.formats=create_encode_decode_formats([self.signals[n] for n in selected],self.message.length)
            self.mask=((1<<(self.message.length*8))-1)^self.formats.padding_mask
            self.active=selected
        raw={}
        for name in selected:
            signal=self.signals[name]; value=values[name]
            if type(value) not in (int,float) or not isfinite(value):
                raise ValueError('重建物理值必须有限: '+name)
            physical=Fraction(str(value)) if exact_values is None else exact_values[name]
            scale=Fraction(str(signal.scale)); offset=Fraction(str(signal.offset))
            if ((signal.minimum is not None and physical<Fraction(str(signal.minimum)))
                    or (signal.maximum is not None and physical>Fraction(str(signal.maximum)))):
                raise ValueError('重建目标物理值越界: '+name)
            code=(physical-offset)/scale
            if signal.is_float:
                raw[name]=float(code)
            else:
                # Fraction的round精确实现最近整数/恰半取偶，负倍率和负值同样适用。
                integer=round(code)
                low=-(1<<(signal.length-1)) if signal.is_signed else 0
                high=(1<<(signal.length-int(signal.is_signed)))-1
                if not low<=integer<=high:
                    raise ValueError('重建码值超出位宽: '+name)
                raw[name]=integer
        fields=[self.signals[n] for n in selected]
        encoded=encode_data(raw,fields,self.formats,scaling=False)
        payload=((int.from_bytes(base.data,'big')&~self.mask)|(encoded&self.mask)).to_bytes(self.message.length,'big')
        decoded=decode_data(payload,self.message.length,fields,self.formats,False,True,False,False)
        facts=[]
        for name in selected:
            signal=self.signals[name]; actual=decoded[name]
            if (not isfinite(actual) or signal.minimum is not None and actual<signal.minimum
                    or signal.maximum is not None and actual>signal.maximum):
                raise ValueError('重建量化后物理值越界: '+name)
            if trace:
                target=Fraction(str(values[name])) if exact_values is None else exact_values[name]
                facts.append((name,float(target),raw[name],actual,float(Fraction(str(actual))-target)))
        return replace(base,data=payload),tuple(facts)

    def close(self):
        """释放本格式缓存，不关闭借用DBC。参数: 无。返回: None。异常: 费用释放错可重试。
        """
        if self._closed:
            return
        self.signals.clear(); self.formats=None; self.message=None; self.active=()
        _release_owned_ram(self,self._fixed_cost,'_fixed_cost'); self._closed=True
