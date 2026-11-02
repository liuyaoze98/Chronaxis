"""核对按需运行编译的真实部分投影、静态完整性和异常借用边界。

输入为合成 memory 计划；通过原适配器、封存历史和绑定工厂取得实际
DecodedBindings，不手工拼造 SHA 或 EOF 证明。仅 current 进入历史，voltage
和 alarm 保留声明。原公共编译作身份对照，根依赖由手写期望核验。
每例只写 work/required-expression-tests 下独占临时目录；真实资源通过
unittest 清理栈关闭并核 RAM 归零。测试不读取私人日志或执行性能测量。
"""

from configuration_fixtures import current_fixture

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan
from chronaxis.core.expression import compile_expression, validate_expression
from chronaxis.execution.bindings import bind_decoded_history
from chronaxis.execution.history import DecodedHistoryStore
from chronaxis.execution.memory_reader import BudgetedMemorySourceAdapter
from chronaxis.execution.required_expression import compile_required_expression
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources import ReadRequest
from test_analysis_plan import ROOT, config_fixture
from test_can_decode_scope_planning import static_only


class RequiredExpressionTests(unittest.TestCase):
    """只在工厂已核真实 EOF 的投影上编译，并检查所有借用资源仍可关闭。"""

    def assert_zero(self, budget):
        """核对所有本例 owner 关闭后的实际账本。

        参数: budget为同例共享ResourceBudget。返回: None。
        异常: 余额不为零使测试失败，不用强制扣款掩盖泄漏。
        """
        self.assertEqual(budget.ram_bytes, 0)

    def fixture(self):
        """建立只有 current 样本的真实历史及保留全部声明的运行绑定。

        参数: 无。返回: (plan, bindings, budget, derived)。
        异常: 原读取、封存、绑定或预算错误传播；清理栈保留真实 owner。
        """
        parent = ROOT / 'work/required-expression-tests'
        parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='home-', dir=parent)
        self.addCleanup(temporary.cleanup)
        config = config_fixture()
        config.update(rules=[], windows=[], calculations=[])
        config['derived'] = dict(twice=dict(expr='magnitude * 2', unit='A'),
            unused_voltage=dict(expr='voltage * 2', unit='V'),
            magnitude=dict(expr='abs(current)', unit='A'))
        with static_only():
            plan = AnalysisPlan.from_dict(current_fixture(config), base_dir=ROOT)
        budget = ResourceBudget(64 * 1024**2)
        self.addCleanup(self.assert_zero, budget)
        definitions = tuple(item.definition for item in plan.signals)
        adapter = BudgetedMemorySourceAdapter(budget, plan.sources[0].config,
            plan.dataset.session_id, definitions, backend='reference')
        self.addCleanup(adapter.close)
        request = ReadRequest(plan.dataset.session_id, ('current',),
            plan.dataset.domain.start_ns, plan.dataset.domain.end_ns, 2)
        history = DecodedHistoryStore(budget, Path(temporary.name) / 'history',
            (adapter.describe(),), {'table': request})
        self.addCleanup(history.close)
        for batch in adapter.iter_batches(request):
            history.append(batch)
        adapter.close()
        history.seal()
        lease = bind_decoded_history(plan.bindings, history)
        self.addCleanup(lease.close)
        self.assertEqual(lease.bindings.sources[0].projected_aliases, ('current',))
        self.assertTrue(lease.bindings.sources[0].source_eof)
        return plan, lease.bindings, budget, tuple(item.definition for item in plan.derived)

    def test_nested_root_with_unused_unprojected_derived_keeps_public_identity(self):
        """嵌套根只要求 current，未投影电压派生仍静态合法，身份与公共公式一致。

        参数: 无。返回: None。异常: 依赖、根树、单位或身份变化即失败。
        """
        plan, bindings, _, derived = self.fixture()
        with static_only():
            static = validate_expression('twice', plan.bindings, derived=derived, unit='A')
            actual = compile_required_expression(static, bindings, derived=derived, unit='A')
            original = compile_expression('twice', bindings, derived=derived, unit='A')
        self.assertEqual(actual, original)
        self.assertEqual(actual.dependencies, ('current',))
        self.assertEqual(actual.root.unit, 'A')
        self.assertIs(actual.bindings, bindings)

    def test_needed_but_unprojected_field_still_fails(self):
        """静态声明不能替代根实际需要的投影证明。

        参数: 无。返回: None。异常: 未投影字段被允许或借用账本改变即失败。
        """
        plan, bindings, budget, derived = self.fixture()
        static = validate_expression('unused_voltage', plan.bindings, derived=derived, unit='V')
        before = budget.ram_bytes
        with self.assertRaisesRegex(ValueError, '未在实际解码投影'):
            compile_required_expression(static, bindings, derived=derived, unit='V')
        self.assertEqual(budget.ram_bytes, before)

    def test_unused_cycle_and_legal_typed_change_are_rejected(self):
        """unused 的非法环和合法内容变化都不能借按需运行绕过原静态身份。

        参数: 无。返回: None。异常: typed 变更被接受即失败。
        """
        plan, bindings, budget, derived = self.fixture()
        static = validate_expression('twice', plan.bindings, derived=derived, unit='A')
        before = budget.ram_bytes
        for text, message in (('unused_voltage', '循环'), ('voltage * 3', '静态表达式不一致')):
            changed = (derived[0], replace(derived[1], expr=text), derived[2])
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, message):
                compile_required_expression(static, bindings, derived=changed, unit='A')
        self.assertEqual(budget.ram_bytes, before)

    def test_original_static_tree_identity_and_domain_are_required(self):
        """根文本、树或摘要被替换仍拒绝，不把同依赖别名当完整静态证明。

        参数: 无。返回: None。异常: 替换内容或错误对象域被接受即失败。
        """
        plan, bindings, _, derived = self.fixture()
        static = validate_expression('twice', plan.bindings, derived=derived, unit='A')
        for variant in (replace(static, text='magnitude'), replace(static, identity='0' * 64),
                replace(static, root=replace(static.root, unit='V')),
                replace(static, dependencies=('voltage',))):
            with self.subTest(variant=variant.text), self.assertRaises(ValueError):
                compile_required_expression(variant, bindings, derived=derived, unit='A')
        with self.assertRaises(TypeError):
            compile_required_expression(static, plan.bindings, derived=derived)
        with self.assertRaises(TypeError):
            compile_required_expression('twice', bindings, derived=derived)

    def test_cancel_and_memory_failure_preserve_exception_and_clear_new_frame(self):
        """取消与内存错原样传播，新编译层不在异常栈额外保留借用绑定。

        参数: 无。返回: None。异常: 错误身份、借用引用或账本边界不符即失败。
        """
        plan, bindings, budget, derived = self.fixture()
        static = validate_expression('twice', plan.bindings, derived=derived, unit='A')
        before = budget.ram_bytes
        for marker in (KeyboardInterrupt('required-expression-cancel'), MemoryError('required-expression-memory')):
            with self.subTest(error=type(marker).__name__):
                caught = None
                with patch('chronaxis.execution.required_expression.validate_expression', side_effect=marker):
                    try:
                        compile_required_expression(static, bindings, derived=derived, unit='A')
                    except BaseException as error:
                        caught = error
                self.assertIs(caught, marker)
                self.assertEqual(budget.ram_bytes, before)
                traceback = caught.__traceback__
                frames = []
                while traceback is not None:
                    if traceback.tb_frame.f_code.co_name == 'compile_required_expression':
                        frames.append(traceback.tb_frame)
                    traceback = traceback.tb_next
                self.assertEqual(len(frames), 1)
                for name in ('static', 'bindings', 'derived', 'checked', 'compiler', 'root', 'payload'):
                    self.assertIsNone(frames[0].f_locals[name])


if __name__ == '__main__':
    unittest.main()
