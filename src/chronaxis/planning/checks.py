"""检查JSON/YAML解析后的配置值，并在错误中保存具体字段位置。

输入为原生字典、列表、标量及JSON路径，输出合法原值、冻结元数据、
时间坐标或模型实例；错误统一关联为PlanValidationError。
字段和类型严格检查，不把True当整数，不忽略未知键或自动纠正数值。
时间必须声明单位或时区，路径只转为绝对定位，不检查文件内容或存在性。
本模块不读日志或DBC；地区时区解析可能读取系统时区数据库。
"""

# 精确配置时间与确定身份只依赖标准库。
import json
import re
from datetime import timedelta, timezone
from math import isfinite
from pathlib import Path
from collections.abc import Mapping
from zoneinfo import ZoneInfo
from difflib import get_close_matches
from ..configuration.diagnostics import child_path, value_preview
# 单位和安全名称校验沿用已验核心。
from ..core.validation import require_identifier, require_text
from ..sources.models import freeze_metadata
from ..timebase import convert_time, parse_duration, parse_datetime_ns


class PlanValidationError(ValueError):
    """保存配置字段路径、原因、机器错误码及可选的原文定位和修正建议。

    不吞执行异常或数据读取失败；code区分无效配置与未接线能力。
    """

    def __init__(self, path: str, message: str, code: str = 'invalid_config', *, hint=None,
                 source=None, location=None, object_name=None, value=None):
        """建立明确路径错误，保留原异常链供load_analysis_plan诊断。

        参数: path为原始字段路径；message为违反的约束；code默认invalid_config。
        hint为修正说明，source/location为文件及行列，object_name为所属声明名称，
        value为有长度限制的显示文本；均可省略，不保存整个原始配置。
        返回: None；异常文本含路径和原因。
        异常: 无；参数由校验器内部构造。
        """
        # 文件路径独立保存在source；path始终指配置字段。
        self.path = path
        # 机器码不以错误文本模糊匹配。
        self.code = code
        # 字段路径与文件分开；只保存有限诊断，不持有加载文档。
        self.message = message
        self.hint=hint
        self.source=source
        self.location=location
        self.object_name=object_name
        self.value_preview=value
        self._diagnostics = None
        self.blocked_checks = ()
        super().__init__()
        self.refresh_text()

    def refresh_text(self):
        """重建人读消息。参数: 无。返回: None。异常: 无；附加定位后调用。"""
        if self._diagnostics is not None:
            text = '\n'.join(f'{index}. {item}' for index, item in enumerate(self._diagnostics, 1))
            if self.blocked_checks:
                text += '\n暂未检查：' + '；'.join(item['path'] + '（' + item['reason'] + '）' for item in self.blocked_checks)
            self.args = (text,)
            return
        place=self.source or ''
        if self.location is not None:
            place+=f':{self.location.line}:{self.location.column}（第{self.location.line}行，第{self.location.column}列）'
        text=(place+' ' if place else '')+self.path+f' [{self.code}] '+self.message
        if self.object_name is not None:
            text+='；对象：'+self.object_name
        if self.value_preview is not None:
            text+='；当前值：'+self.value_preview
        if self.hint is not None:
            text+='；修正：'+self.hint
        self.args=(text,)

    def to_dict(self):
        """返回稳定机器诊断。参数: 无。返回: 原生dict。异常: 无。"""
        return dict(code=self.code,source=self.source,path=self.path,message=self.message,
            line=None if self.location is None else self.location.line,
            column=None if self.location is None else self.location.column,
            object_name=self.object_name,value=self.value_preview,hint=self.hint)

    @property
    def diagnostics(self):
        """返回各项独立诊断。参数: 无。返回: tuple；单错也为一项。异常: 无。"""
        return self._diagnostics if self._diagnostics is not None else (self,)

    @classmethod
    def from_diagnostics(cls, errors, blocked=()):
        """合并错误并保留原类型兼容。参数: 非空错误序列/阻断说明。返回: 异常。异常: 空序列ValueError。"""
        if not errors:
            raise ValueError('诊断集合不能为空')
        if len(errors) == 1 and not blocked:
            return errors[0]
        first = errors[0]
        result = cls(first.path, first.message, first.code)
        result._diagnostics = tuple(errors)
        result.blocked_checks = tuple(blocked)
        result.refresh_text()
        return result


def configuration_error(error):
    """把共享语法错误交给计划API的异常类型。参数: ConfigurationError。返回: PlanValidationError。

    维持文件路径与具体语法代码，文本补实际字段和可靠行列；不读取或重解析配置。
    """
    from ..configuration import field_path_text
    hints={'duplicate_key':'每个对象内的字段名只能声明一次；删除或重命名重复项',
           'unsupported_yaml_feature':'使用普通映射、列表和标量；将公共值明确写入对应字段',
           'nonfinite_number':'使用有限数值，不能用NaN或Infinity代表缺失数据',
           'unsupported_format':'使用 .yaml、.yml 或 .json 文件',
           'invalid_json':'检查引号、逗号和括号；JSON字符串和键必须用双引号',
           'invalid_yaml':'检查缩进和冒号；缩进使用空格'}
    return PlanValidationError(field_path_text(error.field_path),error.message,error.code,
        source=error.source,location=error.location,hint=hints.get(error.code))


def object_at(value, path: str, required=(), optional=()) -> dict:
    """检查JSON对象的类型、必填项和允许字段。

    参数:
        value: 待检查原值，必须是原生dict且全部键为字符串。
        path (str): 当前配置位置。
        required (tuple): 必填键，默认空元组。
        optional (tuple): 可选键，默认空元组。
    返回:
        dict。原字典只在解析中读取，独立快照由计划入口另行创建。
    异常:
        PlanValidationError: 对象类型错误、缺少必填项或含未知键。
    """
    # 不执行任意Mapping用户方法。
    if type(value) is not dict or any(type(key) is not str for key in value):
        # JSON对象键只能文本。
        raise PlanValidationError(path, '必须为字符串键对象','invalid_type',hint='使用字段名: 值组成的对象')
    # 未知键不静默忽略工程参数。
    unknown = sorted(set(value) - set(required) - set(optional))
    # 缺项不能用None隐式补齐。
    missing = sorted(set(required) - set(value))
    # 指向真实错误字段；仅提示候选名称，不改写用户输入。
    if unknown:
        key=unknown[0]
        choices=get_close_matches(key,sorted(set(required)|set(optional)),n=1,cutoff=0.65)
        hint=f'是否要写 {choices[0]}？请核对后修改字段名' if choices else '移除该字段；允许字段：'+', '.join((*required,*optional))
        raise PlanValidationError(child_path(path,key),f'未知字段{unknown}；缺少字段{missing}',
            'unknown_field',hint=hint)
    if missing:
        key=missing[0]
        raise PlanValidationError(child_path(path,key),f'缺少必填字段{missing}',
            'missing_field',hint=f'在所属对象中补充 {key}，值应来自实际输入或分析要求')
    # 深复制由AnalysisPlan入口统一负责。
    return value


def array_at(value, path: str) -> list:
    """要求明确JSON数组，不把文本或tuple当自由迭代器。

    参数: value原值；path位置。
    返回: 原list，仅解析期间读取。
    异常: PlanValidationError为类型错误。
    """
    # from_dict也遵守JSON结构，与load_analysis_plan一致。
    if type(value) is not list:
        # 不接受集合的非确定顺序。
        raise PlanValidationError(path, '必须为数组','invalid_type',hint='使用列表，例如 []')
    # 顺序在后续tuple中保留。
    return value


def text_at(value, path: str, *, identifier=False) -> str:
    """检查非空文本或统一简单名称，保留原大小写。

    参数: value原值；path位置；identifier是否安全标识符。
    返回: 原str，不改点号字段或semantic字符串。
    异常: PlanValidationError为类型/名称错误。
    """
    # 核心校验不需要任何输入I/O。
    try:
        # 字段和标识符采用不同规则。
        return require_identifier(value, path) if identifier else require_text(value, path)
    # 核心异常只在配置边界增加位置。
    except (TypeError, ValueError) as error:
        # 保留原校验原因，不吞异常。
        raise PlanValidationError(path, str(error)) from error


def choice_at(value, choices: tuple, path: str):
    """要求显式支持的原生类型值，禁止bool等价整数。

    参数: value原值；choices允许值tuple；path位置。
    返回: 原值。
    异常: PlanValidationError为未知值/类型。
    """
    # True不能因==1成为config_version合法输入。
    if not any(type(value) is type(item) and value == item for item in choices):
        # 清楚列出真实支持版本/kind。
        raise PlanValidationError(path, f'必须为{choices}','invalid_choice',
            hint='使用允许值之一，例如 '+value_preview(choices[0]))
    # 不自动升级版本或猜别名。
    return value


def number_at(value, path: str, *, integer=False, minimum=None, maximum=None):
    """检查有限原生数值及包含端点的范围，保留整数精度。

    参数:
        value: 原int或float数值，bool不被接受。
        path (str): 当前配置位置。
        integer (bool): 默认False；True时只接受原生int。
        minimum: 可选包含式下限，默认None，不限制下端。
        maximum: 可选包含式上限，默认None，不限制上端。
    返回:
        int或float。保持原类型和位值，不截断或转成浮点。
    异常:
        PlanValidationError: 类型错误、非有限浮点或超出范围。
    """
    # bool不属于数值工程参数。
    if type(value) not in ((int,) if integer else (int, float)) or type(value) is float and not isfinite(value):
        # JSON非有限扩展不进入产品配置。
        raise PlanValidationError(path, '必须为有限整数' if integer else '必须为有限数值','invalid_type')
    # 明确边界不执行隐式截断。
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        # 覆盖率与资源限额不能默默纠正。
        raise PlanValidationError(path, f'数值必须位于[{minimum}, {maximum}]','out_of_range')
    # 保留整数精度与原生类型。
    return value


def duration_at(value, path: str, *, positive=False) -> int:
    """把带单位的非负持续时间转为整数纳秒。

    参数:
        value (str): 明确带时间单位的持续文本，不接受裸数。
        path (str): 当前配置位置。
        positive (bool): 默认False；True时要求纳秒量化后仍大于0。
    返回:
        int。符合int64范围的纳秒时长，允许零时长时返回0。
    异常:
        PlanValidationError: 语法、单位、范围错误，或正时长量化后为0。
    """
    # 原负值在核心入口量化前拒绝。
    try:
        # 不允许裸数或隐式秒。
        result = parse_duration(value).time_ns
    # 将精确转换异常关联配置位置。
    except (TypeError, ValueError, OverflowError) as error:
        # 不修改语义以允许错误参数。
        raise PlanValidationError(path, str(error),'invalid_duration',hint='使用带单位的非负时长，例如 "1s" 或 "500ms"；按实际要求选择') from error
    # 0.1ns舍入0不能冒充正TTL。
    if positive and result <= 0:
        # TTL和抑制窗口必须有正时长。
        raise PlanValidationError(path, '持续量化后必须大于0ns','invalid_duration',hint='设置正时长，例如 "1s"；按实际采样有效期选择')
    # 全部后续时间计算保持整数。
    return result


def coordinate_at(value, path: str, *, absolute=False, tz=None) -> int:
    """解释带单位相对坐标或完整绝对日期，返回整数纳秒。

    参数:
        value (str): 相对数值加s、ms、us或ns单位，或完整绝对日期文本。
        path (str): 当前配置位置。
        absolute (bool): 默认False；True时按绝对日期解析。
        tz (tzinfo | None): 默认None；绝对日期没有自身时区时使用此声明。
    返回:
        int。int64纳秒坐标；相对坐标允许负数，区别于非负持续时间。
    异常:
        PlanValidationError: 文本、单位、时区、日期或数值范围错误。
    """
    # 完整文本保留精确十进制表达。
    text_at(value, path)
    # 核心日期不采用机器默认时区。
    try:
        # 绝对坐标明确完整日期，不猜文件名。
        if absolute:
            # 显式offset日期优先于配置tz。
            return parse_datetime_ns(value, tz).time_ns
        # 相对坐标语法允许负号，显式四种单位。
        match = re.fullmatch(r'\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(ns|us|ms|s)\s*', value)
        # 不接受单位缺失或尾部任意文本。
        if match is None:
            # 负坐标不同于持续参数的非负门槛。
            raise ValueError('坐标须为数值+s/ms/us/ns')
        # 精确转换不先经float。
        return convert_time(match[1], match[2]).time_ns
    # 配置边界保留原转换异常。
    except (TypeError, ValueError, OverflowError) as error:
        # 错误具体关联当前坐标键。
        raise PlanValidationError(path, str(error)) from error


def timezone_at(value, path: str):
    """解析显式UTC、固定offset或IANA名称，拒绝机器时区推断。

    参数: value为None或非空文本；path位置。
    返回: tzinfo或None，仅IANA可能读取系统时区数据库，不读数据输入。
    异常: PlanValidationError为非法offset/未知时区或依赖缺失。
    """
    # 无声明保留None，naive日期稍后必须报错。
    if value is None:
        # 不填机器当前地区。
        return None
    # 时区名称保留用户原文。
    text_at(value, path)
    # UTC常用表示不需外部时区文件。
    if value in ('UTC', 'Z'):
        # 固定零偏移明确UTC。
        return timezone.utc
    # 固定offset只接标准时分格式。
    match = re.fullmatch(r'([+-])(\d{2}):(\d{2})', value)
    # 验证分量，禁止datetime将+00:60自动归一化。
    if match is not None:
        # 各分量界限明确。
        hours, minutes = int(match[2]), int(match[3])
        # 偏移绝对值须小于24小时。
        if hours > 23 or minutes > 59:
            # 不接受非法offset自动变换。
            raise PlanValidationError(path, '固定时区须小于24小时且分钟<60')
        # 正负号只用于声明的固定偏移。
        return timezone(timedelta(minutes=(hours * 60 + minutes) * (1 if match[1] == '+' else -1)))
    # IANA解析可能缺本机tzdata，明确报告而非换机器默认。
    try:
        # 不读取日志/DBC，不凭地理位置猜时区。
        return ZoneInfo(value)
    # 环境缺项与未知名称都是配置可定位错误。
    except (KeyError, ValueError) as error:
        # 保留原依赖/名称异常供调用者修正。
        raise PlanValidationError(path, f'时区不可用：{value}') from error


def metadata_at(value, path: str):
    """深冻结唯一允许自由键的JSON元数据对象。

    参数: value元数据dict；path位置。
    返回: 深复制的只读Mapping/tuple，不影响调用者输入。
    异常: PlanValidationError为非JSON/非有限/键类型错误。
    """
    # 自由键也必须属于JSON对象。
    if type(value) is not dict:
        # 不把数组当metadata根。
        raise PlanValidationError(path, 'metadata必须为对象')
    # 模型递归校验JSON类型且不保留调用者引用。
    try:
        # 自定义键不改变产品执行语义。
        return freeze_metadata(value)
    # 只在配置边界增加当前位置。
    except (TypeError, ValueError) as error:
        # 元数据也不允许未知Python对象进入计划。
        raise PlanValidationError(path, str(error)) from error


def require_json_value(value, path: str, active=None) -> None:
    """在冻结之前检查原生JSON结构，并定位当前递归路径上的循环。

    参数:
        value: dict/list或原生str/int/float/bool/None，浮点必须有限。
        path (str): 当前配置位置，递归时补字段名或数组下标。
        active (set[int] | None): 当前祖先容器身份；根调用省略。
    返回:
        None，结构合法；不复制、转换或修改输入。
    异常:
        PlanValidationError: 非JSON对象、非文本对象键、非有限浮点或循环容器。
    处理流程:
        先区分原生容器与标量，逐层检查后由调用者冻结；共享但不循环的
        容器允许重复出现。此检查不打开文件或执行任意Mapping方法。
    """
    # 只允许JSON原生容器，避免tuple或自定义Mapping被通用冻结器归一化。
    if type(value) not in (dict, list):
        # bool与int都是合法JSON标量；未知对象不调用其转换方法。
        if type(value) not in (str, int, float, bool, type(None)):
            raise PlanValidationError(path, '必须为原生JSON对象、数组或标量')
        # NaN/Infinity不能成为预算、配置元数据或正常数值声明。
        if type(value) is float and not isfinite(value):
            raise PlanValidationError(path, 'JSON浮点必须有限')
        return
    # 当前祖先集合区别于全局访问集合，共享容器不等同于循环。
    ancestors = set() if active is None else active
    identity = id(value)
    if identity in ancestors:
        # 自引用定位在引用发生处，不能泄漏通用冻结器的RecursionError。
        raise PlanValidationError(path, 'JSON配置不能包含循环容器')
    ancestors.add(identity)
    try:
        # 对象只接受字符串键；数组严格保持原顺序和下标。
        if type(value) is dict:
            for key, item in value.items():
                if type(key) is not str:
                    raise PlanValidationError(path, 'JSON对象键必须为字符串')
                require_json_value(item, child_path(path,key), ancestors)
        else:
            for index, item in enumerate(value):
                require_json_value(item, f'{path}[{index}]', ancestors)
    finally:
        # 无论成功或失败都退出当前祖先路径，不污染其他分支的循环判定。
        ancestors.remove(identity)


def json_value(value):
    """将已深冻结JSON快照转回可序列化新结构。

    参数: value来自freeze_metadata的typed结构。
    返回: 新dict/list或原不可变标量。
    异常: 无；调用者保证已校验JSON类型。
    """
    # 只读映射不能直接交给json.dumps。
    if isinstance(value, Mapping):
        # 重建新dict，保持原计划不可变。
        return {key: json_value(item) for key, item in value.items()}
    # tuple表示原JSON数组，顺序必须保留。
    if type(value) is tuple:
        # 不将路径顺序排序。
        return [json_value(item) for item in value]
    # 原生标量不可变，可直接复用。
    return value


def canonical(value) -> str:
    """生成JSON配置的确定身份文本，不读取文件内容。

    参数: value已校验JSON结构或其深冻结快照。
    返回: 规范JSON文本，字典排序、数组原序、整数精度保持。
    异常: TypeError/ValueError为内部非JSON结构。
    """
    # allow_nan=False拒绝非标准JSON，不以NaN身份混入配置。
    return json.dumps(json_value(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def absolute_path(value, base: Path, path: str) -> Path:
    """相对于明确基准解释路径，不打开目标或核实存在性。

    参数:
        value (str): 非空路径文本，不得含NUL字符。
        base (Path): 相对路径的解释基准。
        path (str): 此字段在配置中的错误定位。
    返回:
        Path。绝对定位路径，不解析实际符号链接或读取文件内容。
    异常:
        PlanValidationError: 路径文本非法或含NUL。
        OSError: 获取当前目录或系统路径转换发生错误时可传播。
    """
    # 路径不采用字符串对象隐式repr。
    text_at(value, path)
    # NUL会让未来文件读取不可用，提前具体拒绝。
    if '\x00' in value:
        # 保持配置错误与读文件失败分别诊断。
        raise PlanValidationError(path, '路径含NUL')
    # absolute只调用词法路径操作，不解析符号链接或读取输入。
    return (base / value).absolute()


def model_at(factory, path: str, *args, **kwargs):
    """用内部指定构造器创建模型，将校验错误关联到配置位置。

    参数:
        factory: 程序内部固定的模型构造器或校验函数，不来自配置反射。
        path (str): 当前配置位置。
        args: 已解析的位置参数。
        kwargs: 已解析的关键字参数。
    返回:
        构造器的实际返回值，通常是已检查的模型实例。
    异常:
        PlanValidationError: 包装TypeError、ValueError、OverflowError或LookupError，
            保留原异常链；其他异常原样传播。
    """
    # 构造器来自内部代码，不执行配置指定对象或反射。
    try:
        # 原模型契约直接生效，不隐式修正参数。
        return factory(*args, **kwargs)
    # 只有配置模型校验错误转换为计划异常。
    except (TypeError, ValueError, OverflowError, LookupError) as error:
        # 原单位/时间/字段原因保持可查。
        raise PlanValidationError(path, str(error)) from error
