"""读取明确格式的已解码CSV或TSV信号表，逐批传送归一化信号。

输入是SignalCSVSpec和显式SignalDefinition。构造与describe只检查声明；
实际迭代时才按paths原顺序打开文件，检查表头、列数和来源内时间顺序。
每行每个请求列都是一次观测，缺失文本转None并覆盖旧值，区别于旧Filter
工件中空白表示未更新的政策。数字先保留精确整数，再由选定后端归一化。

输出SignalBatch保留文件、物理行、原文本和时间量化诊断。
batch_rows限制全部列的样本总数；同时间组允许跨文件或跨批，只有更晚
原行或整个来源结束才确认进度。全部paths耗尽才报告source_eof。
请求分析域不用于裁剪原行，开始前的更新仍保留。

本实例管理活动生成器和文件句柄。正常耗尽、读取错误和显式close均尝试
释放资源，清理失败保留读取根因。本模块不调用旧CAN解码，也不重排文件。
"""

# 只使用标准CSV解析，不自动嗅探原始报文格式。
import csv
# 显式类型联合与迭代接口说明资源生命周期。
from collections.abc import Iterator
# Decimal避免整型文本先经过float而失真。
from decimal import Decimal, InvalidOperation
# sys.exception提供当前根因用于清理，不使用frame反射。
import sys
# 文件句柄类型不是无类型object占位。
from typing import TextIO
# 明确的转换定义属于解码之后的分析层。
from ..core.binding import SignalDefinition
# Bool/Enum有不同文本政策，不能Python truthiness。
from ..core.types import SignalDType
from ..core.models import SourceRef
# 当前会话和来源名是安全标识。
from ..core.validation import require_identifier
# 时间字符串统一精确转换并保留量化，offset另显式施加。
from ..timebase.conversion import checked_add_ns, convert_time, parse_datetime_ns
# 来源声明与样本CSV位置是实际公开类型。
from .csv_spec import CSVSourceRef, SignalCSVSpec
# 与memory使用相同字段/转换描述，不复制不同政策。
from .descriptions import describe_fields, source_timebase_identity
# 来源批次/请求与能力严格有类型。
from .models import ReadRequest, SignalBatch, SourceCapabilities, SourceDescription
# 每个有限批次实际调用独立数值后端。
from .packing import pack_decoded
# 跨批协议和根因/关闭错误由公共层定义。
from .protocol import BatchValidator, SourceClosedError, SourceReadError


def choice_text(value: int | bool | str) -> str:
    """生成声明编码对应的CSV文本，区分布尔与整数。

    参数:
        value (int | bool | str): SignalDefinition已检查的原编码。
    返回:
        str。布尔使用'true'或'false'，整数使用十进制文本，字符串保持原样。
    异常:
        无主动异常；调用者须先保证原编码属于允许类型。
    """
    # 布尔文本使用明确小写协议，不使用任意非空字符串真值。
    if type(value) is bool:
        # 不把true写成整数1，编码域保持可区分。
        return 'true' if value else 'false'
    # 已声明整数或字符串按明确文本形式输出，不猜进制。
    return str(value)


class SignalCSVSourceAdapter:
    """按文件声明顺序读取已解码表，每次请求独立保存进度。

    spec固定格式和路径，session_id确定会话，signals与backend决定列转换。
    choices保存声明原编码的文本映射，不缓存随时间变化的值或DBC消息绑定。
    closed、active和handles分别记录关闭标记、活动请求及文件句柄。
    close后拒绝描述和读取。可重复扫描只表示新CSV能再次打开，不授权增加旧链扫描。
    """

    def __init__(self, spec: SignalCSVSpec, session_id: str, signals: tuple[SignalDefinition, ...], *, backend: str = 'numpy', clock_only=(), retain_original=True) -> None:
        """检查来源绑定和声明编码的文本歧义，不读取实际表头。

        参数:
            spec (SignalCSVSpec): 已检查的表格格式、时钟和有序路径声明。
            session_id (str): 本来源所属的会话名称。
            signals (tuple[SignalDefinition, ...]): 当前来源的定义，输出别名须唯一。
            backend (str): 默认'numpy'；也接受'reference'，不自动回退。
            clock_only: 只取更新时间的别名，其单元格不作数值解析。
            retain_original: 默认True保留旧逐行引用；False只使用每列共用身份，不构造原文副本。
        返回:
            None。保存输入和编码映射，初始化活动资源集合。
        异常:
            TypeError: 配置、信号容器或后端类型不合法。
            ValueError: 会话、信号归属、别名冲突，或原码文本与缺失标记有歧义。
        副作用:
            不打开文件；实际字段是否存在在迭代读取时核实。
        """
        # 原始报文CSV不能只有后缀就自动接到此接口。
        if not isinstance(spec, SignalCSVSpec) or not isinstance(signals, tuple) or backend not in ('reference', 'numpy'):
            # 所有输入都先显式解析，未知后端拒绝。
            raise TypeError('signal_csv需要typed spec/signals和明确backend')
        # 会话身份不从文件名或旧缓存继承。
        require_identifier(session_id, 'csv.session_id')
        # 当前来源全部定义必须唯一，其他来源不能借用表列。
        if any(not isinstance(item, SignalDefinition) or item.source != spec.name for item in signals) or len({item.name for item in signals}) != len(signals):
            # 不能取第一个名称冲突或静默跳过他源定义。
            raise ValueError(f'{spec.name}:CSV绑定来源/别名冲突')
        if type(retain_original) is not bool or not set(clock_only)<={item.name for item in signals}:
            raise ValueError('纯时钟字段必须是当前投影，原值保留需要bool')
        self._clock_only,self._retain_original=frozenset(clock_only),retain_original
        self._compact_refs={item.name:SourceRef(session_id,spec.name,item.field) for item in signals} if not retain_original else {}
        # 静态choices文本表只映射已解码值，不涉及DBC消息绑定缓存。
        choices = {}
        # 每个声明编码保持原类型，不对每行重新猜业务标签。
        for definition in signals:
            if definition.name in self._clock_only:
                choices[definition.name]={}
                continue
            # 输入文本必须能唯一对应声明原码。
            pairs = tuple((choice_text(code), code) for code, _ in definition.choices)
            # int1与str1在CSV中不可区分，不能自动挑第一个。
            if len({text for text, _ in pairs}) != len(pairs) or any(text in spec.missing_values for text, _ in pairs):
                # 也不能同时把一个文本声明为正常码和缺失标识。
                raise ValueError(f'{spec.name}:{definition.name}:CSV choices文本歧义/缺失冲突')
            # 保存配置解析结果，不共享任何随时间变化的信号值。
            choices[definition.name] = dict(pairs)
        # 已解析输入与当前后端明确固定。
        self.spec, self.session_id, self.signals, self.backend, self.choices = spec, session_id, signals, backend, choices
        # 当前生命周期与活跃资源只属于本实例。
        self.closed, self.active, self.handles = False, set(), set()

    def _ensure_open(self) -> None:
        """拒绝关闭后操作，重复close本身仍安全。

        参数: 无；读取closed。
        返回: None；开放时无副作用。
        异常: SourceClosedError包含当前来源名。
        """
        # 不能在close后自动重新打开输入延续任务。
        if self.closed:
            # 同步入口直接报告，而不是等下次next。
            raise SourceClosedError(f'{self.spec.name}:source已关闭')

    def describe(self) -> SourceDescription:
        """返回CSV配置描述，保留尚未读取的表头和观测范围状态。

        参数:
            无。读取spec和signals，不打开文件或查询文件状态。
        返回:
            SourceDescription。定位保存有序路径、时间列、单位、偏移和时区，
            观测端点均为None，metadata_status为'declared'。
        异常:
            SourceClosedError: 本实例已经关闭。
            TypeError或ValueError: 字段元数据或描述模型结构错误。
        """
        # 静态查询遵守已关闭状态。
        self._ensure_open()
        # 来源原定位包括有序文件列表，不能从目标列首末伪造范围。
        fields = describe_fields(self.spec.name, self.signals, {'paths': tuple(str(path) for path in self.spec.paths), 'time_column': self.spec.time_column,
                                                             'time_unit': self.spec.unit, 'offset_ns': self.spec.offset_ns,
                                                             'source_timebase_sha256': source_timebase_identity(self.spec.timebase, self.spec.offset_ns),
                                                             'encoding': self.spec.encoding, 'delimiter': self.spec.delimiter, 'missing_values': self.spec.missing_values,
                                                             'timezone': None if self.spec.timezone is None else str(self.spec.timezone)})
        # 正常/错误行诊断来自本parser，raw报文能力明确不支持。
        return SourceDescription(self.spec.name, fields, self.spec.timebase.timebase_id, None, None,
                                 SourceCapabilities(True, False, True, False, ('CSV文件/物理行/原文本/时间量化',),
                                                    ('未读取前表头/观测范围仅声明', 'signal_csv缺失标记为明确MISSING，不用于旧filter未更新工件')), metadata_status='declared')

    def iter_batches(self, request: ReadRequest) -> Iterator[SignalBatch]:
        """创建读取请求生成器，第一次迭代时才打开文件。

        参数:
            request (ReadRequest): 当前会话、投影别名、分析范围及总样本上限。
        返回:
            Iterator[SignalBatch]。保留前置更新；所有文件耗尽后最后一批报告来源结束。
        异常:
            SourceClosedError: 实例已经关闭。
            ValueError: 请求类型、会话或投影别名错误。
            SourceReadError: 实际迭代时失败，附来源、文件、物理行及原异常链。
        副作用:
            登记活动请求；创建迭代器本身不读取表头。
        """
        # 默认不采集首端事实；委托仍执行原同步验证、批次和清理，预算入口不变。
        return self._request_batches(request)

    def _request_batches(self, request: ReadRequest, observation_sink=None, resource_sink=None) -> Iterator[SignalBatch]:
        """创建独立原请求，可选向执行层传递首次扫描的最终观测候选。

        参数: request为原ReadRequest；observation_sink默认None，不增加默认采集；
            非None时为执行层本次读取owner，负责独立资源及最终候选的接收。
            resource_sink默认None，仅为默认预算请求接住生成器和真实清理责任，不采集观测。
        返回: 原SignalBatch生成器；构造只验证并登记，不打开CSV。
        异常: 原SourceClosedError、配置和后续SourceReadError保持；可选sink原错传播。
        副作用: 仅登记当前生成器，其他请求及默认预算协议保持。
        """
        # 生命周期在同步调用边界验证，不隐藏延迟失败。
        self._ensure_open()
        # 本实例只接受ReadRequest，且请求会话必须与构造时一致。
        if not isinstance(request, ReadRequest) or request.session_id != self.session_id:
            # 相同时间数值也不证明会话身份相同。
            raise ValueError(f'{self.spec.name}:CSV请求会话错误')
        # 在打开文件之前拒绝未知请求列。
        validator = BatchValidator(self.describe(), request)
        # wrapper负责清理活动登记，不通过反射查找generator。
        def iterate() -> Iterator[SignalBatch]:
            """转发本次请求，并在任意退出路径移除活动登记。

            参数:
                无。闭包保存当前request、validator及iterator。
            返回:
                每次产生内部读取器提供的SignalBatch，不重复读取或改动进度。
            异常:
                原读取错误传播；finally只移除本请求的登记。
            """
            # 异常、EOF和generator.close共用生命周期。
            try:
                # 保持私有源实际顺序与watermark。
                if observation_sink is None and resource_sink is None:
                    yield from self._iterate(request, validator)
                elif observation_sink is None:
                    yield from self._iterate(request, validator, resource_sink=resource_sink)
                else:
                    yield from self._iterate(request, validator, observation_sink=observation_sink)
            finally:
                # 移除本请求，其他活动请求不受影响。
                self.active.discard(iterator)
        # 私有来源是真正惰性，不在创建请求时读取表头。
        iterator = iterate()
        # 可选owner先接住实际未返回生成器，active登记前后失败仍可关闭同一对象。
        if observation_sink is not None:
            observation_sink._created_iterator(iterator)
        elif resource_sink is not None:
            resource_sink._created_iterator(iterator)
        # close可统一中止已经启动或尚未启动的请求。
        self.active.add(iterator)
        # 交付有实际文件接线的公开迭代器。
        return iterator

    def _parse_value(self, text: str, definition: SignalDefinition) -> int | float | bool | str | None:
        """按缺失标记、原编码和逻辑类型解释单元格文本。

        参数:
            text (str): 原单元格文本，缺失标记精确匹配，不先去除空白。
            definition (SignalDefinition): 当前字段的目标类型与显式转换声明。
        返回:
            int、float、bool、str或None。缺失为None；数学整数先精确转int，
            其他数值用float表示；未声明的字符串编码可交后续归一化层判无效。
        异常:
            ValueError: 布尔文本不合法、数值语法错误、解析资源超限、
                整型转换前小数无法精确表示，或非零小数解析下溢。
        边界:
            非有限数值留给质量检查，不伪装成0。文本和整数展开分别限制4096字符或位。
            本函数只解析原值，不提前做工程缩放或有效期保持。
        """
        # 缺失精确匹配原cell，不strip文本扩大标记范围。
        if text in self.spec.missing_values:
            # 该行明确缺失观测会覆盖旧值，不同于无字段更新。
            return None
        # choices先按明确文本映射原码，随后数值核按原类型映射逻辑值。
        if text in self.choices[definition.name]:
            # 不在此提前做工程缩放或映射到目标标签。
            return self.choices[definition.name][text]
        # 未配置choices的bool只接受明确true/false协议。
        if definition.dtype is SignalDType.BOOL and not definition.choices:
            # 非空字符串和整数1不能靠truthiness变正常True。
            if text not in ('true', 'false'):
                # 任意其他布尔编码必须显式choices。
                raise ValueError(f'{definition.name}:bool文本须为true/false或显式choices')
            # 两个已声明文本保留真正False，不当缺失。
            return text == 'true'
        # 字符串原码的enum/布尔不把未声明文本猜成数值编码。
        if definition.dtype in (SignalDType.ENUM, SignalDType.BOOL) and any(type(code) is str for code, _ in definition.choices):
            # 原文本交给normalize产生OUT_OF_RANGE，而不是自动选首标签。
            return text
        # 有限文本长度限制解析本身，长输入不能构造无界整数。
        if len(text) > 4096:
            # 4096字符上限用于约束数值解析资源，与信号业务阈值无关。
            raise ValueError(f'{definition.name}:数值文本超过4096字符解析限额')
        # Decimal保留整型有效位；无穷/NaN作为无效观测原值后续诊断。
        try:
            # 文本转换不经过float秒或先损失大整数位值。
            number = Decimal(text)
        except InvalidOperation as error:
            # 错误列语法带别名，外层增加文件/物理行。
            raise ValueError(f'{definition.name}:非法数值文本') from error
        # 非有限值不是正常0，由质量核明确NONFINITE。
        if not number.is_finite():
            # 原CSV cell仍在CSVSourceRef保存，诊断不能丢原文。
            return float(number)
        # 数学整数不先转float，含.0/指数的完整整数同样精确。
        if number == number.to_integral_value():
            # 极大指数不能导致无界int分配。
            if number and number.adjusted() >= 4096:
                # 超解析资源直接失败，不生成wrap后的正常样本。
                raise ValueError(f'{definition.name}:整数展开超过4096位解析限额')
            # 原输入是否超64位由独立归一化核附OVERFLOW。
            return int(number)
        # 声明float64的小数按正常binary64表示，原文本定位保留。
        result = float(number)
        # 整型目标仍可显式转换精确小数（如0.5*2），但不可先损失原输入。
        if definition.dtype in (SignalDType.INT64, SignalDType.UINT64) and Decimal.from_float(result) != number:
            # 防止大整数加小数先舍成另一整数后被误标valid。
            raise ValueError(f'{definition.name}:整型转换前小数不能被float64精确表示')
        # 非零小数不可因float下溢变成有效零。
        if result == 0 and number:
            # 不默默补0或放宽normalizer契约。
            raise ValueError(f'{definition.name}:float64解析下溢，不能当有效0')
        # 后续有限性/类型/范围/转换由当前显式归一化政策统一处理。
        return result

    def _close_handle(self, handle: TextIO, primary: BaseException | None) -> None:
        """关闭一个已登记句柄，保留读取根因和清理失败证据。

        参数:
            handle (TextIO): 本实例打开的文件句柄。
            primary (BaseException | None): 已有读取根因；没有时为None。
        返回:
            None。无论关闭成功与否都移除本句柄登记，不删除文件。
        异常:
            关闭错误: 没有根因或primary为GeneratorExit时原样传播；
                已有读取根因时添加附注，保留最初异常。
        """
        # 关闭动作必须执行，不能仅移除登记。
        try:
            # TextIO关闭也可能失败，不能声明已成功完成。
            handle.close()
        except Exception as cleanup:
            # generator正常中止不是业务根因，关闭失败仍应报告。
            if primary is None or isinstance(primary, GeneratorExit):
                # 外层包装来源信息，不能吞掉正常关闭错误。
                raise
            # 错误链保留最初解析/读取异常，附加清理证据。
            primary.add_note(f'{self.spec.name}:文件关闭同时失败：{cleanup}')
        finally:
            # 即使关闭报错也不让实例无界保留引用。
            self.handles.discard(handle)

    def _read_resources(self, request: ReadRequest):
        """为执行层封装提供独立请求的内部资源检查入口。

        参数: request为当前已校验请求。返回: 默认None，直接CSV入口行为不变。
        异常: 执行层子类可在申请预算失败时抛错；不涉及旧报文reader或DBC。
        """
        # 原独立入口不默认创建预算或读取文件；执行层只在子类启用检查。
        return None

    def _iterate(self, request: ReadRequest, validator: BatchValidator, observation_sink=None, resource_sink=None) -> Iterator[SignalBatch]:
        """按原文件顺序逐行读取，保持跨文件的时间组和原行序号。

        参数:
            request (ReadRequest): 当前投影和有限批次样本上限。
            validator (BatchValidator): 本次请求独立的跨批协议检查状态。
            observation_sink: 默认None；执行层可选的本次独立观测接收者，不逐行回调。
            resource_sink: 默认None；只接默认预算请求的资源，不改变first或最终观测候选。
        返回:
            每次产生SignalBatch。最后一批可为空，且source_eof为True。
        异常:
            SourceReadError: 文件、表头、行、时间、数值或协议校验失败；
                保存来源、路径、记录结束物理行及原异常链，清理错误不覆盖根因。
        处理流程:
            每个文件打开后验证表头，按请求列解析原值并记录逐样本位置。
            缓冲满时先发布已有样本；更晚原行证明上一组完整。
            单文件结束不重置时间、序号或缓冲；所有文件结束后确认最后时间组。
            退出时关闭句柄和清空缓冲，不修改已经返回的数组。
        """
        # 显式投影保持请求顺序，分析层列选择不改变旧路径。
        selected = tuple(next(item for item in self.signals if item.name == name) for name in request.signal_names)
        # 有限pending包含记录与逐样本物理位置，不存全文件rows。
        pending, count, previous, watermark, sequence = {}, 0, None, None, 0
        # 只有可选采集保存首端；末端和原时间行数复用原previous、sequence，不看投影样本。
        first = None
        # 路径/行号即使open失败也有可读位置。
        path, line, reader, resources = self.spec.paths[0], 0, None, None
        # 读取/转换错误统一带当前真实来源位置。
        try:
            # 检查器在文件打开前申请固定读取/协议开销；每个请求独立关闭。
            if observation_sink is not None:
                resources = observation_sink._read_resources()
            elif resource_sink is not None:
                resources = resource_sink._read_resources()
            else:
                resources = self._read_resources(request)
            # 配置paths原序，不能排序、预读或重排文件。
            for path in self.spec.paths:
                # 新文件即使open失败，也不沿用前一个文件的错误行号。
                line, reader = 0, None
                # 关闭之后不能开始下一文件。
                self._ensure_open()
                # newline空串由csv解释换行，编码显式，只读输入。
                handle = path.open('r', encoding=self.spec.encoding, newline='')
                # 可选owner在活动set登记前接住真实句柄，登记取消也有恢复责任。
                if observation_sink is not None:
                    observation_sink._opened_handle(handle)
                elif resource_sink is not None:
                    resource_sink._opened_handle(handle)
                # 活跃句柄在close/cancellation时可追踪。
                self.handles.add(handle)
                # 单文件生命周期不重置协议时钟/sequence/pending。
                try:
                    # strict拒绝损坏引号，原表头文本完整保留。
                    reader = csv.reader(handle if resources is None else resources.lines(handle), delimiter=self.spec.delimiter, strict=True)
                    # 预算包装只控制原reader的next，不替换CSV解释或记录物理行计数。
                    records = reader if resources is None else resources.records(reader)
                    # 空文件无表头不能证明声明字段，header-only表合法。
                    header = next(records, None)
                    # 最新物理行用于错误定位与引用。
                    line = reader.line_num
                    # 导出表末尾多余分隔符形成的匿名列可忽略；保留原宽度，逐行确认这些列确实没有数据。
                    header_width = 0 if header is None else len(header)
                    named_width = header_width
                    while header is not None and named_width and header[named_width - 1] == '':
                        named_width -= 1
                    header = None if header is None else header[:named_width]
                    # 中间空名、仅空白的名字和重名仍拒绝；已声明但未请求的字段也必须能够定位。
                    if header is None or any(not name.strip() for name in header) or len(set(header)) != len(header) or self.spec.time_column not in header or any(item.field not in header for item in self.signals):
                        # 不凭字段下标猜含义或把缺列当全UNKNOWN。
                        hint = '；文件含BOM时请将reader.encoding设为utf-8-sig' if header and header[0].startswith('\ufeff') else ''
                        raise ValueError('CSV表头缺失/重名/声明字段无法定位' + hint)
                    # 静态列索引只作用已解码表，不是DBC绑定缓存。
                    indexes = {name: position for position, name in enumerate(header)}
                    # 每文件实际逐行读取，没有第二次输入扫描。
                    for cells in records:
                        # 保存记录结束的物理行号，使引号内多行记录仍可追溯。
                        line = reader.line_num
                        # 空物理行没有时间观测，不伪造新样本。
                        if not cells:
                            # 不reset前一状态或whole-source进度。
                            continue
                        # 允许省去表尾匿名空单元格；有名列不能缺失，也不能多出表头未声明的列。
                        if not named_width <= len(cells) <= header_width:
                            # 原cell错误明确报当前文件/行。
                            raise ValueError('CSV行列数与表头不同')
                        if any(value != '' for value in cells[named_width:]):
                            raise ValueError('CSV尾部匿名列包含非空数据，需要填写列名')
                        # 关闭可中止当前源，不继续读取后续数据。
                        self._ensure_open()
                        # 时间先精确转换，Date必须明确offset或source_timezone。
                        time_text = cells[indexes[self.spec.time_column]]
                        # 只有明确absolute ISO单位使用日期解析。
                        conversion = parse_datetime_ns(time_text, self.spec.timezone) if self.spec.unit == 'ISO8601' else convert_time(time_text, self.spec.unit)
                        # 固定offset在整数ns域安全施加，不推断同步。
                        time = checked_add_ns(conversion.time_ns, self.spec.offset_ns)
                        # 跨文件回退也拒绝，不重排旧输入以掩盖错误。
                        if previous is not None and time < previous:
                            # 单文件EOF不能允许时间重置。
                            raise ValueError('来源时间回退（含连续文件边界）')
                        # 必须经过转换、offset和顺序检查，空投影与缺失值原行仍算观测。
                        if first is None and (observation_sink is not None or
                                resource_sink is not None and resource_sink.observe_bounds):
                            first = time
                            if resource_sink is not None:
                                resource_sink.observed_start=time
                        # 下一真实时间更晚才完整越过上一组。
                        if previous is not None and time > previous:
                            # 观测事实与进度保证分开保存。
                            watermark = previous
                        # 每请求列在该行是实际观测，缺失标记也传MISSING更新。
                        for definition in selected:
                            # 原文本只定位一次；预算层可在数组峰值达到容量前提前交批。
                            text = '' if definition.name in self._clock_only else cells[indexes[definition.field]]
                            if count == request.batch_rows or (resources is not None and
                                    resources.should_flush(time_text, text, definition, validator)):
                                # 数组/字符串定宽提升和协议集合副本必须在分配之前预留。
                                if resources is not None:
                                    resources.before_pack(pending, validator)
                                # 当前组未完整时watermark仍留在上一组。
                                batch = self._make_batch(pending, watermark, False, None)
                                # 跨批结构/身份/承诺验证后才交付。
                                validator.accept(batch)
                                # 校验成功后转为当前owned数组和当前组身份的持有预算。
                                if resources is not None:
                                    resources.after_pack(validator)
                                # 返回owned列，下一缓冲与当前批断开。
                                yield batch
                                # 只释放传输原记录，不reset持续/进度状态。
                                pending, count = {}, 0
                                # yield恢复后才释放原缓冲；交接时当前数组仍由检查器持有。
                                if resources is not None:
                                    resources.clear_pending()
                            # CSV引用会保留原文本，在解析、构造引用和append之前申请。
                            if resources is not None:
                                resources.before_sample(time_text, text, path, definition)
                            # 原生标量随后只应用一次当前额外转换。
                            value = None if definition.name in self._clock_only else self._parse_value(text, definition)
                            # 每样本保留物理行/原字段和原文本/时间量化。
                            reference = (CSVSourceRef(self.session_id, self.spec.name, definition.field, str(path), line, time_text, text, conversion.quantized)
                                if self._retain_original else self._compact_refs[definition.name])
                            # 原序号在整个配置来源内递增，单文件结束时不重置。
                            pending.setdefault(definition.name, []).append((time, sequence, value, reference))
                            # 上限口径为所有列样本总数。
                            count += 1
                        # 即使空投影，该原行也推进源实际时间/原序号。
                        previous, sequence = time, sequence + 1
                finally:
                    # 根因可能为读取错误或正常generator.close，分别处理关闭失败。
                    try:
                        if observation_sink is None and resource_sink is None:
                            self._close_handle(handle, sys.exception())
                        elif observation_sink is None:
                            resource_sink._close_handle(handle, sys.exception())
                        else:
                            observation_sink._close_handle(handle, sys.exception())
                    finally:
                        # 预算模式保留最新实际物理行，再丢文件局部引用后释放表头/行。
                        if resources is not None:
                            line = reader.line_num if reader is not None else line
                            header = indexes = cells = reader = records = None
                            if observation_sink is None and resource_sink is None:
                                resources.end_file()
                            elif observation_sink is None:
                                resource_sink._end_file(resources, sys.exception())
                            else:
                                # 此处捕获正在传播的解析、取消或文件关闭主错，清理附加错不能盖掉它。
                                observation_sink._end_file(resources, sys.exception())
            # 所有paths才whole-source EOF；实际末点不补周期。
            watermark = previous if previous is not None else watermark
            # header-only或空投影末点仍是源实际事实，空来源可以None。
            if resources is not None:
                # EOF也可能有剩余样本，不能绕过数组/协议检查。
                resources.before_pack(pending, validator)
            batch = self._make_batch(pending, watermark, True, previous)
            # EOF承诺通过同一个跨batch validator。
            validator.accept(batch)
            if resources is not None:
                resources.after_pack(validator)
            # 最终validator与after_pack均通过才交候选；接收者仍须等真正StopIteration及清理成功。
            if observation_sink is not None:
                observation_sink._accept_candidate(first, previous, sequence)
            if resource_sink is not None and resource_sink.observe_bounds:
                resource_sink.observed_end=previous
            # 最后批次可含剩余样本或为空。
            yield batch
        except Exception as error:
            # csv.reader在取下一record时也会抛错，line应反映已消费物理行。
            line = reader.line_num if reader is not None else line
            # 保留最初cause/关闭附注，位置绝不使用当前机器时间代替。
            raise SourceReadError(f'{self.spec.name}:{path}:{line}:signal_csv读取失败：{error}') from error
        finally:
            # 释放有限原记录，已返回owned输出不受影响。
            pending.clear()
            # 原错误或取消都触发本请求预算抵销，不删除输入文件。
            if resources is not None:
                if observation_sink is None and resource_sink is None:
                    resources.close()
                elif observation_sink is None:
                    resource_sink._close_resources(sys.exception())
                else:
                    observation_sink._close_resources(sys.exception())

    def _make_batch(self, pending, watermark: int | None, eof: bool, observed_end: int | None) -> SignalBatch:
        """归一化当前缓冲中的原值，保留逐样本CSV位置。

        参数:
            pending (dict): 别名到(time_ns, sequence, 原值, CSVSourceRef)记录列表。
            watermark (int | None): 完整时间组的进度坐标，单位为纳秒。
            eof (bool): 整个来源是否耗尽。
            observed_end (int | None): 实际观测终点纳秒坐标，未知时为None。
        返回:
            SignalBatch。每列与当前位置记录对应，未知端点不补0。
        异常:
            TypeError、ValueError或OverflowError: 数值、时间或列结构校验失败；外层附读取位置。
        副作用:
            分配批次列，不额外读取输入，也不继承其他请求的信号值。
        """
        # 当前声明不共享原信号值/跨任务绑定缓存。
        definitions = {item.name: item for item in self.signals}
        # 三元原值记录与四元CSV位置分开装箱，位置不会混入数值矩阵。
        columns = {name: pack_decoded(definitions[name], tuple((time, sequence, value) for time, sequence, value, _ in records),
                                     tuple(reference for _, _, _, reference in records), self.backend,
                                     retain_original=self._retain_original,clock_only=name in self._clock_only) for name, records in pending.items()}
        # 输出真实会话/来源/watermark/终点，未知不补0。
        return SignalBatch(self.spec.name, self.session_id, columns, watermark, eof, observed_end)

    def close(self) -> None:
        """尝试关闭全部活动请求和句柄，最后报告最初清理失败。

        参数:
            无。读取closed、active和handles。
        返回:
            None。重复调用直接返回；原输入文件保留。
        异常:
            SourceReadError: 至少一次清理失败，原异常链保存首错，其他失败作为附注。
        副作用:
            先标记关闭，再逐个清理生成器和残留句柄，最后清空资源登记。
        """
        # 幂等关闭不会重复删除或执行输入读取。
        if self.closed:
            # 已清理实例不自动重开。
            return
        # 先拒绝后续调用，再逐个尝试所有资源清理。
        self.closed, failure = True, None
        # generator.close触发单文件finally，未启动generator也安全。
        for iterator in tuple(self.active):
            # 一个关闭失败也不能跳过其他活动请求。
            try:
                # 释放读取进度和有限原值缓冲。
                iterator.close()
            except Exception as error:
                # 首错作为根因，其他错误另作附注。
                if failure is None:
                    # 不用最后一个错误覆盖最初错误。
                    failure = error
                else:
                    # 保留所有清理失败但最终只抛一个带来源的错误链。
                    failure.add_note(f'其他CSV请求关闭失败：{error}')
        # 残留句柄也尝试关闭，不依赖生成器已经启动。
        for handle in tuple(self.handles):
            # _close_handle用相同根因保护政策。
            try:
                # 没有根因时close失败应成为failure。
                self._close_handle(handle, failure)
            except Exception as error:
                # 原failure为None才会从helper抛错。
                failure = error
        # 所有引用清空，输入文件本身保留。
        self.active.clear()
        # 活跃句柄登记不延续到其他session。
        self.handles.clear()
        # 若任一资源清理失败，明确报告错误，不能声称清理成功。
        if failure is not None:
            # 将清理失败交给调用方，后续执行器须据此判断整体任务状态。
            raise SourceReadError(f'{self.spec.name}:signal_csv关闭失败') from failure
