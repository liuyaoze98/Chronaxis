"""把单帧数值公式准备成直接读取解码字典的函数，按原始到达顺序累计。

修复版 base 可传只含原生数值尺度的算式；配置入口另传公共编译器核过的
program，以保留 v4 在表达式内部插入的单位换算。两条路径都不执行用户代码。
"""

import ast
import math
import operator


_LIMITS = {'int64': (-(1 << 63), (1 << 63) - 1), 'uint64': (0, (1 << 64) - 1)}
_BINARY = {'add': operator.add, 'sub': operator.sub, 'mul': operator.mul, 'div': operator.truediv}
_SYNTAX = {ast.Add: 'add', ast.Sub: 'sub', ast.Mult: 'mul', ast.Div: 'div'}


def _float(value):
    """转换有限且可精确转双精度的数值；拒绝 bool 和非有限值。"""
    if type(value) not in (int, float):
        raise ValueError('需要物理解码后的数值')
    result = float(value)
    if not math.isfinite(result) or result != value:
        raise ValueError('非有限数值或整数转 float64 丢失精度')
    return result


def _typed(value, dtype):
    """检查定宽整数范围、整数性或双精度可表示性，返回目标原生数值。"""
    if dtype == 'float64':
        return _float(value)
    if dtype not in _LIMITS or type(value) not in (int, float):
        raise ValueError('需要已声明的数值类型')
    low, high = _LIMITS[dtype]
    if not low <= value <= high or type(value) is float and not value.is_integer():
        raise ValueError(f'{dtype} 溢出或小数精度丢失')
    return int(value)


def _number_type(value):
    """为已检查的数值常量确定低层公式的自然类型。"""
    if type(value) is float:
        _float(value)
        return 'float64'
    if type(value) is not int:
        raise ValueError('常量必须为数值')
    dtype = 'uint64' if value > _LIMITS['int64'][1] else 'int64'
    _typed(value, dtype)
    return dtype


def _affine(value, scale, offset, dtype):
    """按一个完整仿射变换检查最终类型，允许摄氏到开尔文的合法抵消。"""
    if dtype == 'float64' or not all(type(v) is int for v in (value, scale, offset)):
        value, scale, offset = _float(value), _float(scale), _float(offset)
    total = value * scale + offset
    if total == 0 and offset == 0 and value != 0 and scale != 0:
        raise ValueError('单位换算下溢')
    return _typed(total, dtype)


def encode_program(node):
    """将公共 ExprNode 的数值子集编码为普通 dict。其他操作准备时即拒绝。"""
    op = node.operator
    if op not in {*_BINARY, 'name', 'const', 'abs', 'neg', 'to_float', 'unit_convert'}:
        raise ValueError(f'fast 不支持表达式操作 {op}')
    result = {'op': op, 'dtype': node.dtype.value}
    if op == 'name':
        result['name'] = node.name
    elif op == 'const':
        result['value'] = node.value
    else:
        result['args'] = [encode_program(child) for child in node.args]
        if op == 'unit_convert':
            result['scale'], result['offset'] = node.value
    return result


def _syntax(text, signals, parameters):
    """将受限的原尺度公式转换为节点；不解析属性、容器或任意函数。"""
    if type(text) is not str or not 0 < len(text) <= 4096:
        raise ValueError('逐帧公式必须是非空且不超过4096字符的文本')
    tree = ast.parse(text, mode='eval')
    if sum(1 for _ in ast.walk(tree)) > 512:
        raise ValueError('逐帧公式过长')

    def literal(value):
        return dict(op='const', dtype=_number_type(value), value=value)

    def visit(node):
        if isinstance(node, ast.Constant):
            return literal(node.value)
        if isinstance(node, ast.Name):
            if node.id in parameters:
                return literal(parameters[node.id])
            if node.id not in signals:
                raise ValueError(f'未知信号或参数 {node.id}')
            return dict(op='name', name=node.id, dtype=signals[node.id]['dtype'])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            if isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant) and type(node.operand.value) in (int,float):
                return literal(-node.operand.value)
            child = visit(node.operand)
            return child if isinstance(node.op, ast.UAdd) else dict(op='neg', dtype=child['dtype'], args=[child])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'abs' and len(node.args) == 1 and not node.keywords:
            child = visit(node.args[0])
            return dict(op='abs', dtype=child['dtype'], args=[child])
        if isinstance(node, ast.BinOp) and type(node.op) in _SYNTAX:
            left, right = visit(node.left), visit(node.right)
            op = _SYNTAX[type(node.op)]
            dtype = 'float64' if op == 'div' or 'float64' in (left['dtype'],right['dtype']) else left['dtype']
            return dict(op=op, dtype=dtype, args=[left, right])
        raise ValueError('fast 公式仅支持数值、名称、加减乘除、正负号和 abs')
    return visit(tree.body)


def _bind(node, signals, depth=0):
    """在准备阶段创建标量运算函数，运行时只传当帧的解码字典。"""
    if depth > 128 or type(node) is not dict:
        raise ValueError('无效或过深的逐帧数值指令')
    op, dtype = node['op'], node['dtype']
    if dtype not in ('float64', 'int64', 'uint64'):
        raise ValueError('逐帧累计需要数值输出')
    if op == 'const':
        constant = _typed(node['value'], dtype)
        return lambda values: constant
    if op == 'name':
        signal = signals[node['name']]
        if dtype != signal['dtype']:
            raise ValueError('指令中的信号类型与声明不符')
        key = signal['signal']
        scale, offset = signal.get('scale', 1), signal.get('offset', 0)
        _number_type(scale)
        _number_type(offset)
        original = signal.get('input_dtype', dtype)
        if scale == 1 and offset == 0 and original == dtype:
            return lambda values: _typed(values[key], dtype)
        return lambda values: _affine(_typed(values[key], original), scale, offset, dtype)
    args = [_bind(child, signals, depth + 1) for child in node['args']]
    if len(args) == 2 and op in _BINARY:
        left, right = args
        combine = _BINARY[op]
        if dtype == 'float64':
            return lambda values: _float(combine(_float(left(values)), _float(right(values))))
        return lambda values: _typed(combine(left(values), right(values)), dtype)
    if len(args) == 1:
        child, = args
        if op == 'to_float':
            return lambda values: _float(child(values))
        if op in ('neg', 'abs'):
            unary = abs if op == 'abs' else operator.neg
            return lambda values: _typed(unary(child(values)), dtype)
        if op == 'unit_convert':
            scale, offset = node['scale'], node['offset']
            _number_type(scale)
            _number_type(offset)
            return lambda values: _affine(child(values), scale, offset, dtype)
    raise ValueError(f'无效的数值指令 {op}')


class _Accumulator:
    """按原顺序累加已经求好的贡献，不解析公式或保存解码字段。"""

    def __init__(self, spec):
        """读取结果名称和单位；新累计器没有观测值，不把空输入记为零。"""
        self.name, self.unit = spec['name'], spec['unit']
        self.matched = self.selected = 0
        self.total = 0.0

    def add(self, contribution, keep):
        """提交一条已核验贡献；溢出时保留此前累计及计数，原异常传播。"""
        if keep:
            self.total = _float(self.total + contribution)
            self.selected += 1
        self.matched += 1

    def result(self):
        """返回当前业务行；区分没有目标、空方向桶和贡献相消。"""
        reason = None if self.selected else 'no_selected_direction' if self.matched else 'no_target_frames'
        return dict(name=self.name, unit=self.unit, value=self.total if self.matched else None,
                    status='complete' if self.matched else 'indeterminate', reason=reason)


class _Metric(_Accumulator):
    """当前文件的求值器和累计状态；先求公式和方向，再提交本条贡献。"""

    def __init__(self, spec, formula):
        super().__init__(spec)
        self.evaluate = formula
        self.factor = _float(spec.get('output_scale', 1))
        self.direction = None
        if spec.get('direction') is not None:
            direction = spec['direction']
            if direction['bucket'] not in ('positive','negative'):
                raise ValueError('方向桶需要 positive 或 negative')
            self.direction = (direction['signal'], direction['bucket'] == 'positive')

    def consume(self, decoded):
        """消费一条已匹配记录。除零、溢出或缺值直接使本文件失败。"""
        contribution, keep = self.contribution(decoded)
        self.add(contribution, keep)

    def contribution(self, decoded):
        """只求当前帧贡献和方向选择，不修改累计状态。

        参数: decoded为DBC物理数值字典。返回: (float64贡献, bool入选)。
        异常: 类型、单位换算、公式或方向值错误；未入桶也必须先求值。
        """
        contribution = _float(self.evaluate(decoded))
        if self.factor != 1:
            contribution = _affine(contribution, self.factor, 0, 'float64')
        keep = True
        if self.direction is not None:
            key, positive = self.direction
            value = decoded[key]
            _number_type(value)
            keep = value > 0 if positive else value < 0
        return contribution, keep

def prepare_metric(spec):
    """创建一个计算项的求值/累计状态。参数为简单声明字典；拒绝冲突别名和未知指令。"""
    signals, parameters = spec['signals'], spec.get('parameters', {})
    if signals.keys() & parameters.keys():
        raise ValueError('参数与信号名称冲突')
    natural = _syntax(spec['expr'], signals, parameters)
    return _Metric(spec, _bind(spec.get('program', natural), signals))


def _prepare_program_metric(spec):
    """绑定内部已检查的指令，不重新解析原公式。

    参数: spec来自公共 fast 编译器，或本会话已经检查的低层声明。
    返回: 每文件独立的求值/累计状态。异常: 指令、类型或数值声明错误。
    仅内部调用；普通字典入口仍通过 prepare_metric 检查文本，即使带有 program。
    """
    signals = spec['signals']
    if signals.keys() & spec.get('parameters', {}).keys():
        raise ValueError('参数与信号名称冲突')
    return _Metric(spec, _bind(spec['program'], signals))


def _check_program_spec(spec):
    """为低层会话检查一次文本及指令，并返回带指令的新声明。

    参数: 原计算项字典，不修改它。返回: 浅复制的内部声明。
    异常: 与 prepare_metric 相同；非法文本不能借合法 program 绕过检查。
    """
    signals, parameters = spec['signals'], spec.get('parameters', {})
    if signals.keys() & parameters.keys():
        raise ValueError('参数与信号名称冲突')
    natural = _syntax(spec['expr'], signals, parameters)
    checked = dict(spec, program=spec.get('program', natural))
    _prepare_program_metric(checked)
    return checked
