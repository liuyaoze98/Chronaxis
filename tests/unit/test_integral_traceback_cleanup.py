"""检查积分归约失败后，原异常栈不继续拥有已抵费用的面积列。

从真实CalculationSeries计算普通/条件、参考/NumPy面积项，真实ResourceBudget与
两个独立归约owner负责费用。只在实际预约、事实安装、数组ufunc和工作费释放
边界注入同一个取消对象，保留异常与原traceback后检查弱引用、外部guard和借款。
NumPy观察器透传真实运算，不伪造数值；参考容量错误来自真实partial_limit。
本专项不清任何外部帧，不运行旧reader、不计时，也不把外部回调主动保留的值
纳入产品能回收的承诺。对应BUG-M2-182的同一条面积临时资源链。
"""

# 真实上下文恢复patch，补丁退出后才关闭owner并核对预算。
from contextlib import ExitStack
import gc
import unittest
from unittest.mock import patch
from weakref import ref
import numpy as np

# 两种真实面积模型都由既有独立后端计算生成，不伪造预算owner。
from chronaxis.core.calculations import CalculationSeries, CalculationDefinition
from chronaxis.core.models import Interval
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D
from chronaxis.core.integral_terms_reference import compute_integral_terms_reference
from chronaxis.core.integral_terms_numpy import compute_integral_terms_numpy
from chronaxis.core.conditional_integral_terms_reference import compute_conditional_integral_terms_reference
from chronaxis.core.conditional_integral_terms_numpy import compute_conditional_integral_terms_numpy
from chronaxis.core.integral_sum import IntegralStateLimitError
import chronaxis.core.integral_sum_reference as reference_sum_module
from chronaxis.execution.integral_reduction import IntegralReduction
from chronaxis.execution.conditional_integral_reduction import ConditionalIntegralReduction
from chronaxis.results.budget import ResourceBudget


def make_terms(conditional, backend, values=(1.0, 2.0, 3.0)):
    """用完整合成轴实际生成面积列和覆盖事实，绑定身份与owner保持一致。

    参数: conditional选择显式全TRUE条件；backend选择独立后端；values为每秒W值。
    返回: 对应真实冻结Terms，末0仅提供EOF边界，不增加面积。
    异常: 现有模型或计算检查错误原样传播，不绕过真实类型门槛。
    """
    # 当前三秒域与原时间戳先以整数ns构造，不用面积值假冒原始采样。
    spec = CalculationDefinition('area', 'integral', Interval(0, 3_000_000_000))
    condition = tuple(ScalarValue(True, D.BOOL) for _ in range(4)) if conditional else None
    series = CalculationSeries(spec.window, (0, 1_000_000_000, 2_000_000_000, 3_000_000_000),
        tuple(ScalarValue(value, D.FLOAT64) for value in values + (0.0,)),
        (True,) * 4, 'W', condition, binding_identity='traceback-test')
    # 后端各自生成值和掩码，不能把NumPy输出转换为参考输入作唯一真值。
    compute = ((compute_conditional_integral_terms_reference if backend == 'reference'
                else compute_conditional_integral_terms_numpy) if conditional else
               (compute_integral_terms_reference if backend == 'reference'
                else compute_integral_terms_numpy))
    return compute(series, spec)


def external_forward(owner, terms, *, finish=False):
    """代表调用方帧：保留guard，同时自行结束借入terms的临时引用。

    参数: owner为真实归约，terms为真实输入；finish选择实际完成阶段。
    返回: 原push/finish返回。异常: 不包装原异常，外部guard必须留在原traceback。
    """
    external_guard = {'must_survive': 'external-frame'}
    try:
        return owner.finish() if finish else owner.push(terms)
    finally:
        # 测试调用方主动不保留输入；产品不能靠清这个外部帧来让弱引用消失。
        terms = None


class AddObserver:
    """透传真正np.add，仅记录accumulate实际返回数组的弱引用。"""

    def __init__(self, operation, weak_arrays, highs):
        """登记真实ufunc与仅含弱引用的有限观察列表。

        参数: operation为原np.add；两个list接收弱引用。返回: None。异常: 无主动异常。
        """
        self.operation, self.weak_arrays, self.highs = operation, weak_arrays, highs

    def accumulate(self, *args, **kwargs):
        """执行实际累积并观察结果，不替换任何浮点运算或形状。

        参数: 原ufunc参数。返回: 原真实ndarray。异常: 原异常；观察器不额外保活参数。
        """
        result = None
        try:
            result = self.operation.accumulate(*args, **kwargs)
            self.highs.append(ref(result))
            self.weak_arrays.append(('actual_highs', ref(result)))
            return result
        finally:
            # 本测试回调也不借故障栈保存数组；外部guard则刻意保留。
            self = args = kwargs = result = None


class IntegralTracebackCleanupTests(unittest.TestCase):
    """真实owner关闭后保留异常，检查本层数组与purekernel状态释放。"""

    def exercise(self, conditional, backend, stage, *, after=True):
        """执行一次有精确命中的真实故障，关闭主owner并保护活sibling与777借款。

        参数: conditional/backend指定路径；stage为reserve/facts/sum/release/round/reference_limit/
            reference_validation；
            after控制实际reserve或facts动作执行前后，其他故障在指定真实运算后。
        返回: 含原异常、原TB、资源弱引用和目标命中数的有限dict。
        异常: 故障未命中、清账或sibling错误由unittest断言报告；清理错误不隐藏。
        """
        budget = ResourceBudget()
        budget.reserve_ram(777)
        spec = CalculationDefinition('area', 'integral', Interval(0, 3_000_000_000))
        # 活sibling有真实资源槽；主owner关闭不能按总余额猜测并抵掉另一层费用。
        sibling = IntegralReduction(budget, spec, spec.window, 'W', 'traceback-test', backend='reference')
        baseline = budget.ram_bytes
        owner = (ConditionalIntegralReduction if conditional else IntegralReduction)(
            budget, spec, spec.window, 'W', 'traceback-test', backend=backend,
            partial_limit=1 if stage == 'reference_limit' else 4096)
        values = ((1e16, 1.0, -1e16) if stage == 'reference_limit' else
                  (1e16, 1.0, 1e-16) if stage == 'round' else (1.0, 2.0, 3.0))
        terms = make_terms(conditional, backend, values)
        weak_objects = [('terms_model', ref(terms)), ('pure_kernel', ref(owner._kernel))]
        if backend == 'numpy':
            weak_objects.extend((('areas', ref(terms.areas)), ('valid', ref(terms.valid)),
                                 ('initial_partials', ref(owner._kernel._partials))))
        marker = KeyboardInterrupt('actual-integral-' + stage)
        caught = None
        hits = 0
        highs = []
        actual_reserve, actual_release = budget.reserve_ram, budget.release_ram
        actual_facts = owner._facts_owner.push
        actual_concat, actual_add = np.concatenate, np.add
        actual_finite, actual_subtract = np.isfinite, np.subtract
        actual_reference_finite = reference_sum_module.isfinite
        workspace = 4096 + 64 * len(terms.areas)

        def reserve(amount):
            """仅当前真实预约前后抛同一marker。参数: bytes。返回: 不正常返回。异常: 原marker。"""
            nonlocal hits
            hits += 1
            if after:
                actual_reserve(amount)
            raise marker

        def facts(value):
            """在真实事实安装前后取消。参数: 实际Facts。返回: 不正常返回。异常: 原marker。"""
            nonlocal hits
            try:
                hits += 1
                if after:
                    actual_facts(value)
                raise marker
            finally:
                value = None

        def concatenate(*args, **kwargs):
            """观察真实chain等新数组。参数: 原参数。返回: 原ndarray。异常: 原错误。"""
            result = actual_concat(*args, **kwargs)
            weak_objects.append(('actual_concatenate', ref(result)))
            return result

        def finite(value, *args, **kwargs):
            """真实isfinite只在已观察highs处取消。参数: 原参数。返回: 原掩码。异常: 同一marker。"""
            nonlocal hits
            result = None
            try:
                result = actual_finite(value, *args, **kwargs)
                if any(item() is value for item in highs):
                    hits += 1
                    raise marker
                return result
            finally:
                value = args = kwargs = result = None

        def subtract(*args, **kwargs):
            """完成实际rounding差列后取消。参数: 原参数。返回: 不正常返回。异常: 同一marker。"""
            nonlocal hits
            result = None
            try:
                result = actual_subtract(*args, **kwargs)
                weak_objects.append(('actual_rounding_subtract', ref(result)))
                hits += 1
                raise marker
            finally:
                args = kwargs = result = None

        def release(amount):
            """只在本次工作费真正释放后取消。参数: bytes。返回: 原结果。异常: 同一marker。"""
            nonlocal hits
            result = actual_release(amount)
            if amount == workspace:
                hits += 1
                raise marker
            return result

        def reference_finite(value):
            """原有限性谓词返回后取消。参数: 原生float。返回: 不正常返回。异常: 同一marker。"""
            nonlocal hits
            try:
                actual_reference_finite(value)
                hits += 1
                raise marker
            finally:
                value = None

        try:
            # round在真实完整push之后观察finish；其他故障都在同一push调用链。
            if stage == 'round':
                owner.push(terms)
            with ExitStack() as stack:
                if stage == 'reserve':
                    stack.enter_context(patch.object(budget, 'reserve_ram', reserve))
                elif stage == 'facts':
                    stack.enter_context(patch.object(owner._facts_owner, 'push', facts))
                elif stage in ('sum', 'round'):
                    stack.enter_context(patch.object(np, 'concatenate', concatenate))
                    stack.enter_context(patch.object(np, 'add', AddObserver(actual_add, weak_objects, highs)))
                    stack.enter_context(patch.object(np, 'isfinite' if stage == 'sum' else 'subtract',
                                                    finite if stage == 'sum' else subtract))
                elif stage == 'release':
                    stack.enter_context(patch.object(budget, 'release_ram', release))
                elif stage == 'reference_validation':
                    stack.enter_context(patch.object(reference_sum_module, 'isfinite', reference_finite))
                # reference_limit无替代数值函数，由实际第二误差项触发硬容量错误。
                try:
                    external_forward(owner, terms, finish=stage == 'round')
                except BaseException as error:
                    caught = error
        finally:
            # 调用方不人为留下输入。关闭时仍完整保留原异常和TB以暴露任何callee漏引用。
            terms = None
            owner.close()
        self.assertIsNotNone(caught)
        if stage == 'reference_limit':
            self.assertIsInstance(caught, IntegralStateLimitError)
        else:
            self.assertIs(caught, marker)
            self.assertEqual(hits, 1)
        traceback = caught.__traceback__
        self.assertTrue(owner.closed)
        self.assertEqual(budget.ram_bytes, baseline)
        self.assertFalse(sibling.closed)
        # 主owner关闭后，同账本另一个真实owner仍可完整计算并关回借款基线。
        sibling.push(make_terms(False, 'reference'))
        sibling.finish()
        self.assertEqual(sibling.result.value, 6.0)
        sibling.close()
        self.assertEqual(budget.ram_bytes, 777)
        budget.release_ram(777)
        self.assertEqual(budget.ram_bytes, 0)
        gc.collect()
        return {'error': caught, 'traceback': traceback, 'weak_objects': weak_objects,
                'highs_count': len(highs), 'hits': hits}

    def assert_reclaimed(self, observation):
        """保原TB检查真实资源弱引用全部失效，且调用方guard不被清理。

        参数: exercise返回的有限观察。返回: None。异常: 资源或TB/guard变化由断言报告。
        """
        self.assertIs(observation['error'].__traceback__, observation['traceback'])
        for name, handle in observation['weak_objects']:
            self.assertIsNone(handle(), name)
        # 只检查外部帧的声明guard，不对每个内部变量写实现镜像断言。
        cursor = observation['traceback']
        external_frames = []
        while cursor is not None:
            if cursor.tb_frame.f_code is external_forward.__code__:
                external_frames.append(cursor.tb_frame)
            cursor = cursor.tb_next
        self.assertEqual(len(external_frames), 1)
        self.assertEqual(external_frames[0].f_locals.get('external_guard'),
                         {'must_survive': 'external-frame'})

    def test_real_reserve_and_facts_faults_drop_borrowed_terms_for_both_backends(self):
        """普通/条件两核预约及真实事实安装前后失败均结束terms借期。

        参数: 无。返回: None。异常: 原错、资源、借款、sibling或TB差异由断言报告。
        """
        for conditional in (False, True):
            for backend in ('reference', 'numpy'):
                for stage in ('reserve', 'facts'):
                    for after in (False, True):
                        with self.subTest(conditional=conditional, backend=backend, stage=stage, after=after):
                            self.assert_reclaimed(self.exercise(conditional, backend, stage, after=after))

    def test_actual_numpy_advance_temporaries_and_old_partial_views_are_reclaimed(self):
        """真实accumulate后故障，chain/highs/旧state视图和输入列均不被TB钉住。

        参数: 无。返回: None。异常: 原错、实际目标未命中或弱引用仍活由断言报告。
        """
        for conditional in (False, True):
            with self.subTest(conditional=conditional):
                observation = self.exercise(conditional, 'numpy', 'sum')
                self.assertGreater(observation['highs_count'], 0)
                self.assert_reclaimed(observation)

    def test_reference_real_capacity_failure_releases_model_and_numeric_state(self):
        """参考原生容量错误保留类型/TB，关闭后不留模型或purekernel状态。

        参数: 无。返回: None。异常: 容量错误被替换、模型或guard保活由断言报告。
        """
        for conditional in (False, True):
            with self.subTest(conditional=conditional):
                self.assert_reclaimed(self.exercise(conditional, 'reference', 'reference_limit'))

    def test_reference_validation_cancel_leaves_no_hidden_input_iterator(self):
        """有限性检查取消不以自有生成式的隐藏zip保留完整参考输入tuple。

        参数: 无。返回: None。异常: 原marker、guard或本模块隐式迭代器残留由断言报告。
        """
        for conditional in (False, True):
            with self.subTest(conditional=conditional):
                observation = self.exercise(conditional, 'reference', 'reference_validation')
                self.assert_reclaimed(observation)
                # 改前已在两条真实链证明.0 zip持values/valid；只约束本模块的该资源路径。
                cursor = observation['traceback']
                while cursor is not None:
                    frame = cursor.tb_frame
                    self.assertFalse(frame.f_globals.get('__name__') == reference_sum_module.__name__
                                     and frame.f_code.co_name == '<genexpr>')
                    cursor = cursor.tb_next

    def test_rounding_failure_clears_reverse_views_and_finish_self_reference(self):
        """真实finish舍入差列故障后，保TB也不让reverse或self延长状态费用寿命。

        参数: 无。返回: None。异常: 原marker或真实数组/状态未释放由断言报告。
        """
        for conditional in (False, True):
            with self.subTest(conditional=conditional):
                self.assert_reclaimed(self.exercise(conditional, 'numpy', 'round'))

    def test_release_after_cancel_does_not_keep_installed_candidate_or_double_credit(self):
        """真正释放工作费后取消，已安装候选仍随owner关闭且不重复抵借款。

        参数: 无。返回: None。异常: 原异常、预算或候选生命周期差异由断言报告。
        """
        for conditional in (False, True):
            for backend in ('reference', 'numpy'):
                with self.subTest(conditional=conditional, backend=backend):
                    self.assert_reclaimed(self.exercise(conditional, backend, 'release'))


if __name__ == '__main__':
    # 直接运行只执行本专项；导入不会创建owner、数组或外部文件。
    unittest.main()
