"""列出已实现内置逐点函数的固定签名与编译、质量、更新和后端契约。

本目录供宿主查询现行版本的能力，不创建数据、运行回调或扩大AST白名单。
编译器及对应数值内核负责实际检查；注册时以内置名称集合消除冲突。
"""
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class BuiltinFunctionContract:
    """只读的内置函数契约。字符串描述明确参数、常量、输出、失效与更新政策。"""
    name: str
    version: str
    signature: str
    inputs: str
    constants: str
    output: str
    validity: str
    updates: str = '普通表达式依赖的真实更新'
    history_ns: int = 0
    pure: bool = True
    backends: tuple = ('reference','numpy')


def _catalog(version):
    """构造一个版本的真实内置目录。参数: 4。返回: 只读名称映射。异常: 内部描述冲突。"""
    spec_version = 'functions-v4-b6'
    items = {}
    def add(name,args,inputs,constants,output,validity,updates='普通表达式依赖的真实更新'):
        """登记单一语义描述。参数: 固定签名及规则文本。返回: None。异常: 重复名称。"""
        if name in items:
            raise ValueError('重复的内置函数描述')
        items[name] = BuiltinFunctionContract(name,spec_version,f'{name}({args})',inputs,constants,output,validity,updates)
    add('abs','x','数值','维持操作数尺度','同型绝对值与输入单位','输入原因；int64最小值溢出')
    add('isclose','a,b,*,atol,rtol','可比较数值','非负有限字面量容差，rtol无量纲',
        'BOOL、单位1','输入或浮点中间量失效；非对称相对误差')
    add('quantity','value,unit','有限数值字面量','单位须已登记的字符串字面量',
        '指定尺度和对应数值dtype','非法常量静态拒绝','无真实样本更新')
    add('to_unit','x,unit','兼容量种的数值','显式单位字面量','目标尺度；必要时提升float64',
        '不兼容静态拒绝；逐样本检查精度/范围')
    add('where','condition,when_true,when_false','BOOL条件与兼容数值','单一声明尺度适配裸数',
        '分支公共数值类型与单位','条件未知不选分支；只合并活动路径原因','真实活动分支更新、切换或未知恢复')
    for name in ('minimum','maximum'):
        add(name,'a,b,*rest','至少两个兼容数值','歧义裸常量须quantity','共同类型和规范尺度',
            '任一必要输入未知传播，不忽略缺通道')
    add('clip','x,lower,upper','三个兼容数值','静态边界判序；歧义须quantity','共同类型和规范尺度',
        '运行期倒置DOMAIN_ERROR，必要输入缺失传播')
    add('square','x','可平方的数值单位','保留定宽及适用的单位换算','数值及单位平方','定宽或浮点溢出失效')
    add('sqrt','x','可开方的已知量种','先归一化尺度','float64、平方根量种','负数或精度失败无效')
    add('mod','a,b','单位1的同型整数','裸整数按定宽适配','原整数dtype、单位1',
        '零除数无效；余数随除数符号')
    for name,args,output in (('bit_test','x,bit','BOOL'),('bit_extract','x,start,width','uint64')):
        add(name,args,'单位1整数的64位补码','静态位号/宽度不能越出0到63',
            output+'、单位1','原输入无效传播')
    for name in ('to_int64','to_uint64','to_float64'):
        add(name,'x','数值','显式选择的尺度优先，否则使用规范尺度',name[3:]+'、所选单位',
            '精度损失或超出目标定宽无效')
    add('enum_code','x','具有code_dtype的枚举来源','不接受标签字符串','原整数代码、单位1',
        '独立原码质量，不将标签索引当代码')
    add('lookup','x,table,*,mode="linear",bounds="invalid"','兼容表轴单位的数值',
        '已声明表名以及mode、bounds为字符串字面量','表输出单位；linear为float64，阶梯按表声明',
        '精度与边界检查；只有显式clamp才夹紧越界位置')
    return MappingProxyType(items)


_CURRENT = _catalog(4)


def builtin_function_specs(config_version=4):
    """查询指定语法版本的内置函数。参数: 配置版本4。返回: 只读契约映射。异常: 未支持版本。"""
    if type(config_version) is not int or config_version != 4:
        raise ValueError('内置函数目录仅支持配置4')
    return _CURRENT
