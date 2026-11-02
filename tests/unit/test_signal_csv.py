"""读取合成信号表，检查类型、跨文件边界、错误位置和关闭行为。

输入为小型CSV夹具，或测试在work专用目录生成的错误表；输出为unittest
断言和保留的诊断文件。两后端按原文件顺序读取，并与相同内存原值比较；
时间量化、大整数、空白无效观测、枚举映射及同刻跨文件组分别检查。
读取失败后仍须关闭句柄；关闭也失败时不能掩盖最初读取错误。静态描述
不打开文件，实际迭代才验证数据。输出只写新work，不改RefProjects；
诊断文件被Git忽略，不递归清理用户目录。信号表空白政策与旧报文工件分开。
"""

# 标准库测试与明确错误夹具替换，不改已冻结输入。
import unittest
# 配置差异只属于各独立测试，不修改全局声明。
from dataclasses import replace
# absolute日期测试使用明确fixed offset，不能靠机器时区。
from datetime import timedelta, timezone
# 输入和工作目录都相对于本仓库实际路径。
from pathlib import Path
# 模拟仅用于失败/清理边界，正常测试使用真实CSV文件。
from unittest.mock import patch
# 每测试有唯一专用工作目录，保留诊断而不覆盖用户文件。
from uuid import uuid4
# 数组事实比较保留int64/float64/bool物理域。
import numpy as np
# 模型与显式转换沿用M1，不从列名猜单位。
from chronaxis.core.binding import SignalDefinition
# 参考相同memory原值来源。
from chronaxis.core.models import MemoryRow, SourceSpec, TimebaseSpec
# 类型/时基是通用公共契约。
from chronaxis.core.types import SignalDType, TimeType
# 被测入口是真实CSV来源，memory仅为独立已解码输入对照。
from chronaxis.sources import CSVSourceRef, MemorySourceAdapter, ReadRequest, SignalCSVSourceAdapter, SignalCSVSpec, SourceClosedError, SourceReadError

# 当前仓库根由测试所在位置明确确定，不读取历史快照。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 小合成固定表可纳入源码，区别于真实私人日志。
FIXTURE_ROOT = PROJECT_ROOT / 'tests' / 'fixtures' / 'signals'


class SignalCSVTests(unittest.TestCase):
    """真实表读入/错误/关闭测试各自有独立实例和新工作目录。"""

    def setUp(self) -> None:
        """声明路径、信号与唯一诊断目录，不扫描旧资源。

        参数: 无；每测试建立新局部输入。
        返回: None；不创建根目录副本文档或写旧快照。
        异常: 工作目录/合法夹具错误直接失败。
        """
        # 每测试写入受控workspace/work路径，测试结束保留诊断文件。
        self.directory = PROJECT_ROOT / 'work' / 'unit_signal_csv' / uuid4().hex
        # 只创建明确新测试目录，不清理其他任务数据。
        self.directory.mkdir(parents=True)
        # 全部adapter由tearDown关闭，不共享上次进度。
        self.adapters = []
        # 两个文件明确属于同一合成时基/来源，保持给定顺序。
        self.spec = SignalCSVSpec('table', (FIXTURE_ROOT / 'continuous_1.csv', FIXTURE_ROOT / 'continuous_2.csv'), TimebaseSpec('clock', TimeType.RELATIVE, 'csv-continuous-v1'), 'time_s', 's')
        # 每列每行明确观测，与旧filter的未更新空白不同。
        self.signals = (SignalDefinition('voltage', 'table', 'voltage', SignalDType.FLOAT64, 'V', 10_000_000_000),
                        SignalDefinition('current', 'table', 'current_mA', SignalDType.FLOAT64, 'A', 10_000_000_000, input_unit='mA', scale=.001),
                        SignalDefinition('identifier', 'table', 'identifier', SignalDType.INT64, '1', 10_000_000_000),
                        SignalDefinition('alarm', 'table', 'alarm', SignalDType.BOOL, '1', 10_000_000_000))

    def tearDown(self) -> None:
        """关闭测试创建的所有来源，诊断文件原样保留。

        参数: 无；读取当前测试adapter列表。
        返回: None；不删除用户路径或输入夹具。
        异常: 未预期的关闭错误应令测试失败，不吞异常。
        """
        # 正常/断言失败共用清理，每次close幂等。
        for adapter in self.adapters:
            # 只关闭本测试实际创建的实例。
            adapter.close()

    def write(self, name: str, content: str) -> Path:
        """把声明为合成的错误表写入专用目录。

        参数: name为单文件名；content为明确小CSV文本。
        返回: 新Path，目录固定在workspace/work。
        异常: OSError为写失败，路径越界ValueError。
        """
        # 只允许普通文件名，防止测试拼接到其他用户目录。
        if Path(name).name != name:
            # 不执行跨目录删除或覆盖。
            raise ValueError('测试name只接受文件名')
        # 新路径由已创建唯一目录决定，不覆盖固定夹具。
        path = self.directory / name
        # UTF-8小合成输入，文件本身不附加破坏schema的设备字段。
        path.write_text(content, encoding='utf-8')
        # 本轮Docs验证报告关联这些受控输入与work设备标签。
        return path

    def adapter(self, backend: str = 'numpy', *, spec=None, signals=None) -> SignalCSVSourceAdapter:
        """建立并登记一个真实CSV来源实例。

        参数: backend明确；spec/signals可为该测试的特定声明。
        返回: SignalCSVSourceAdapter，不打开输入。
        异常: 配置错误直接传播，不猜默认文件格式。
        """
        # None才使用当前合法夹具，空signals不是隐式默认。
        adapter = SignalCSVSourceAdapter(self.spec if spec is None else spec, 'session', self.signals if signals is None else signals, backend=backend)
        # 记录资源以供断言失败后仍正常关闭。
        self.adapters.append(adapter)
        # 返回实际被测来源，不使用伪数据接口。
        return adapter

    def request(self, size: int = 1, names: tuple[str, ...] = ('voltage', 'current', 'identifier', 'alarm')) -> ReadRequest:
        """创建显式投影/域/样本总数限制。

        参数: size为batch_rows；names明确别名tuple。
        返回: ReadRequest，domain [0,6s]包括末点上下文。
        异常: 结构/时间/限额错误传播。
        """
        # 读取不得把域当成额外旧扫描/下推权限。
        return ReadRequest('session', names, 0, 6_000_000_000, size)

    def facts(self, batches, *, references: bool = True) -> dict:
        """还原当前小测试的列事实，不作为生产全量结果模型。

        参数: batches是小夹具输出；references控制是否比较不同源定位。
        返回: 别名到时间/原序号/值/有效性/质量/原值及可选ref的列表。
        异常: 错误结构直接失败，不通过广播补齐。
        """
        # 测试规模有限，生产AnalysisRunner应磁盘暂存/流式结果。
        result = {}
        # 输出别名/异步列保留原输入，不拼float宽矩阵。
        for batch in batches:
            # 同一个原行多个列各有自己的来源。
            for name, column in batch.series.items():
                # 逐输出仅比较事实，不进行数值内核运算。
                for i in range(len(column.time_ns)):
                    # 无效值占位不能进入正常输出比较。
                    value = (column.labels[int(column.values[i])] if column.labels else column.values[i].item()) if column.valid[i] else None
                    # 整数时间/序号/标识必须保持原位值。
                    fact = (int(column.time_ns[i]), int(column.sequence[i]), value, bool(column.valid[i]), int(column.quality[i]), column.original_values[i])
                    # 不同来源的物理定位另外验收，而非伪装相等。
                    result.setdefault(name, []).append(fact + ((column.source_ref[i],) if references else ()))
        # 顺序不是按batch编号定义，切分不影响比较结果。
        return result

    def test_real_continuous_files_and_memory_equivalence(self) -> None:
        """验证两后端/四切分、同刻跨文件及相同memory原值。

        参数: 无；固定匿名两个连续表。
        返回: None；数值/质量/序号/文件行/组承诺不随切分改变。
        异常: 断言失败表示接线/类型/完整组错误。
        """
        # 正常真实文件不能由mock输出替代。
        baseline = None
        # 每后端独立归一化，批1使四列同组必然跨批。
        for backend in ('reference', 'numpy'):
            # batch2/7/all检验文件边界任意落在传输缓冲中间。
            for size in (1, 2, 7, 100):
                # 完整来源只读一次，返回typed列与CSVSourceRef。
                adapter = self.adapter(backend)
                # 实际读取从next开始，不额外预读文件。
                batches = list(adapter.iter_batches(self.request(size)))
                # 总28样本，batch上限按四列和。
                self.assertEqual(sum(batch.sample_count for batch in batches), 28)
                # 一批都不得以宽表行数绕样本限制。
                self.assertTrue(all(batch.sample_count <= size for batch in batches))
                # 全部文件才EOF，单文件结束不reset时间/sequence。
                self.assertEqual([batch.source_eof for batch in batches], [False] * (len(batches) - 1) + [True])
                # 实际EOF为6s，不补额外一个周期。
                self.assertEqual(batches[-1].observed_end_ns, 6_000_000_000)
                # 正常耗尽后资源集合为空，尚未close也没有泄漏。
                self.assertEqual((len(adapter.active), len(adapter.handles)), (0, 0))
                # 同一完整事实跨后端/批大小保持严格相等。
                facts = self.facts(batches)
                # 只用于测试的首基线仍有下方手算核对。
                if baseline is None:
                    # 原路径/行号也是结果事实，不只比数值。
                    baseline = facts
                else:
                    # 不通过丢掉CSVSourceRef让切分表面相等。
                    self.assertEqual(facts, baseline)
        # mA→A转换恰一次，2s真实同刻两条仍完整保留。
        self.assertEqual([item[2] for item in baseline['current']], [10., 10., 0., 0., 20., 0., 0.])
        # 全7行标识大于2**53保持整数，不进入float矩阵。
        self.assertEqual([item[2] for item in baseline['identifier']], [2 ** 53 + 1] * 7)
        # 第二文件同刻t2的原行序号继续3，物理行2。
        ref = baseline['current'][3][-1]
        # 完整实际来源/字段/文件/物理行/文本均可定位。
        self.assertIsInstance(ref, CSVSourceRef)
        # 没有用第一个文件引用覆盖第二文件的同刻记录。
        self.assertEqual((Path(ref.path).name, ref.line_number, ref.field, ref.time_text, ref.value_text), ('continuous_2.csv', 2, 'current_mA', '2', '0'))
        # 相同memory完整原值输入独立接线，不能拿旧错误输出作真值。
        times, currents, alarms = (0, 1, 2, 2, 3, 5, 6), (10000, 10000, 0, 0, 20000, 0, 0), (False, True, False, False, True, False, False)
        # MemoryRow关键字明确，避免此前001夹具参数顺序问题。
        rows = tuple(MemoryRow(time_ns=time * 1_000_000_000, sequence=i, values={'voltage': 400, 'current_mA': current, 'identifier': 2 ** 53 + 1, 'alarm': alarm}) for i, (time, current, alarm) in enumerate(zip(times, currents, alarms)))
        # 同样合成时基/当前来源，声明终点6秒，不伪造观察范围。
        source = SourceSpec('table', self.spec.timebase, rows, observation_start_ns=0, observation_end_ns=6_000_000_000)
        # 原值进入独立内存adapter，与CSV已解析同种原值比较。
        memory = MemorySourceAdapter(source, 'session', self.signals, backend='reference')
        # 只比较数值/质量/序号，物理文件定位与内存本来不同。
        self.assertEqual(self.facts(list(memory.iter_batches(self.request(7))), references=False), {name: [item[:-1] for item in items] for name, items in baseline.items()})
        # 内存对照同样释放来源生命周期。
        memory.close()

    def test_describe_and_request_are_lazy(self) -> None:
        """验证static describe和请求创建不打开输入，运行失败带路径。

        参数: 无；声明不存在的CSV路径。
        返回: None；未知范围保留None/declared，next才实际尝试读取。
        异常: 断言失败表示提前读文件或虚构验证结果。
        """
        # 不存在路径是允许静态解释的声明，不是verified能力证据。
        spec = replace(self.spec, paths=(self.directory / 'missing.csv',))
        # spy若被调用即失败，证明describe/iter入口无输入I/O。
        with patch.object(Path, 'open', side_effect=AssertionError('unexpected pre-read')) as opened:
            # 构造/描述只基于配置元数据。
            adapter = self.adapter(spec=spec)
            # 必需范围unknown，不从dataset.domain猜覆盖。
            description = adapter.describe()
            # 创建真实惰性生成器，也不读表头。
            iterator = adapter.iter_batches(self.request())
            # 静态source.time/fields已声明但未核实物理文件。
            self.assertEqual((description.observation_start_ns, description.observation_end_ns, description.metadata_status), (None, None, 'declared'))
            # 确认所有静态操作都没有额外读取。
            opened.assert_not_called()
        # 真正next时缺文件必须失败，不能返回正常空来源。
        with self.assertRaisesRegex(SourceReadError, 'table:.*missing.csv:0') as caught:
            # 错误包含准确新文件行号0，保留FileNotFound根因。
            next(iterator)
        # 最初异常没有被关闭或统计覆盖。
        self.assertIsInstance(caught.exception.__cause__, FileNotFoundError)
        # 失败生成器与句柄都释放。
        self.assertEqual((len(adapter.active), len(adapter.handles)), (0, 0))

    def test_bad_rows_and_original_file_order(self) -> None:
        """拒绝坏表头/行/时间/数值/引号和连续文件回退。

        参数: 无；专用work中明确错误小表。
        返回: None；错误带文件/物理行，路径不排序重试。
        异常: 断言失败表示错误被吞或输入被静默修正。
        """
        # 每错误只保留必要列，避免其他缺列掩盖当前问题。
        cases = ('time_s,current_mA,current_mA\n0,1,2\n', 'time_s,other\n0,1\n', 'time_s,current_mA\n0\n',
                 'time_s,current_mA\nwrong,1\n', 'time_s,current_mA\n2,1\n1,1\n', 'time_s,current_mA\n0,bad-number\n',
                 'time_s,current_mA\n0,"unclosed\n')
        # 按文件逐一真实读入，不通过mock伪造解析。
        for index, content in enumerate(cases):
            # 每坏表是明确新路径，不覆写已有fixture。
            path = self.write(f'bad_{index}.csv', content)
            # 仅声明current输入，不需要业务语义目录。
            adapter = self.adapter(spec=replace(self.spec, paths=(path,)), signals=self.signals[1:2])
            # 数据/语法失败必须向调用者抛SourceReadError。
            with self.assertRaisesRegex(SourceReadError, 'table:.*bad_') as caught:
                # 不因异常返回正常EOF或丢掉坏行。
                list(adapter.iter_batches(self.request(1, ('current',))))
            # 坏引号在获取下一record之前抛错，仍应报告真正消费的第2行。
            if index == 6:
                # 不能沿用表头1行，002回归不放宽来源定位要求。
                self.assertIn('bad_6.csv:2:', str(caught.exception))
            # 失败资源不留句柄/活动迭代器。
            self.assertEqual((len(adapter.handles), len(adapter.active)), (0, 0))
        # 反转两个正常文件是用户给定但回退的输入，不自动排序修复。
        reversed_adapter = self.adapter(spec=replace(self.spec, paths=tuple(reversed(self.spec.paths))))
        # 第一文件末6秒后第二文件起0秒应明确拒绝。
        with self.assertRaisesRegex(SourceReadError, '来源时间回退'):
            # strict paths顺序保留，不预扫描按时间排序。
            list(reversed_adapter.iter_batches(self.request(100)))

    def test_missing_precision_and_nonfinite_values(self) -> None:
        """核对每行缺失覆盖、大整数转float精度和非有限原因。

        参数: 无；明确time_ns/W列及NA标记。
        返回: None；正常1000/0与UNKNOWN区分，两个后端掩码一致。
        异常: 断言失败表示先转float、补零或丢原文本。
        """
        # .0结尾的大整数也是精确整数，不能先舍入后假装有效。
        path = self.write('quality.csv', 'time_ns,x\n0,1000\n1,NA\n2,9007199254740993.0\n3,NaN\n4,inf\n5,0\n')
        # 缺失标记明确列为NA/空字符串；原时间单位ns。
        spec = replace(self.spec, paths=(path,), time_column='time_ns', unit='ns', missing_values=('', 'NA'))
        # 浮点输出的整数转换仍执行M1精确表示检查。
        signal = SignalDefinition('power', 'table', 'x', SignalDType.FLOAT64, 'W', 10)
        # 两个后端都从同原文本真实读取，不用一方结果当另一方输入。
        for backend in ('reference', 'numpy'):
            # 一大批可比较全部typed列，读取没有隐式额外period。
            batches = list(self.adapter(backend, spec=spec, signals=(signal,)).iter_batches(self.request(100, ('power',))))
            # 原行已完整，同时间没有重叠冲突。
            column = batches[0].series['power']
            # 1000和0有效，缺失/大整数precision/NaN/Inf各自无效。
            np.testing.assert_array_equal(column.quality, [0, 1, 128, 8, 8, 0])
            # 无效占位不参与正常值断言。
            np.testing.assert_array_equal(column.values[column.valid], [1000., 0.])
            # 原整数位值和原CSV文本都保留，不能只剩舍入值。
            self.assertEqual((column.original_values[2], column.source_ref[2].value_text), (2 ** 53 + 1, '9007199254740993.0'))
        # 非零极小小数不能解析为正常float0。
        underflow = self.write('underflow.csv', 'time_ns,x\n0,1e-10000\n')
        # 明确失败比虚构有效0可靠，错误带具体字段及位置。
        with self.assertRaisesRegex(SourceReadError, '解析下溢'):
            # source无额外reader重试或默认值。
            list(self.adapter(spec=replace(spec, paths=(underflow,)), signals=(signal,)).iter_batches(self.request(100, ('power',))))
        # 非整型小数若先舍入成另一个大整数会破坏int64契约。
        bad_integer = self.write('integer.csv', 'time_ns,x\n0,9007199254740993.1\n')
        # 目标类型改INT64仍需在精度损失之前拒绝，非整数原值不能冒充标识。
        with self.assertRaisesRegex(SourceReadError, '小数不能被float64精确表示'):
            # 原单位1/原列x明确，不用测试预期放宽结果。
            list(self.adapter(spec=replace(spec, paths=(bad_integer,)), signals=(replace(signal, dtype=SignalDType.INT64),)).iter_batches(self.request(100, ('power',))))

    def test_time_quantization_absolute_and_timezone(self) -> None:
        """验收整数纳秒half-even与ISO显式时区，不使用机器默认。

        参数: 无；两个相邻细粒度时间与两个absolute时间表。
        返回: None；原文本/量化标志与精确offset坐标保留。
        异常: 断言失败表示float epoch或naive时间被猜测。
        """
        # .5ns和1.5ns先half-even到0/2，再明确+100ns。
        path = self.write('quantized.csv', 'time_ns,x\n0.5,1\n1.5,2\n')
        # 固定offset不是同步证明，但合法声明会准确施加。
        spec = replace(self.spec, paths=(path,), time_column='time_ns', unit='ns', offset_ns=100)
        # 原值为int64，这条测试关注时间不丢位值。
        signal = SignalDefinition('x', 'table', 'x', SignalDType.INT64, '1', 10)
        # 实际读入源而非测试自己调用时间转换。
        column = list(self.adapter(spec=spec, signals=(signal,)).iter_batches(self.request(100, ('x',))))[0].series['x']
        # 已量化时间/原文共同保存，不能修改原timestamp。
        np.testing.assert_array_equal(column.time_ns, [100, 102])
        # 原cell及量化诊断每行可追溯。
        self.assertEqual([(ref.time_text, ref.time_quantized) for ref in column.source_ref], [('0.5', True), ('1.5', True)])
        # naive日期明确+08:00，亚微秒1ns/2ns不能被datetime截断。
        absolute = self.write('absolute.csv', 'time_iso,x\n1970-01-01T08:00:00.000000001,1\n1970-01-01T08:00:00.000000002,2\n')
        # absolute时基不接受relative origin，时区由调用者给出。
        absolute_spec = replace(spec, paths=(absolute,), time_column='time_iso', unit='ISO8601', offset_ns=0,
                                timebase=TimebaseSpec('utc', TimeType.ABSOLUTE), timezone=timezone(timedelta(hours=8)))
        # 真正CSV日期转换得到UTC epoch整数坐标。
        dates = list(self.adapter(spec=absolute_spec, signals=(signal,)).iter_batches(self.request(100, ('x',))))[0].series['x']
        # 没有经过float epoch或微秒datetime保存ns。
        np.testing.assert_array_equal(dates.time_ns, [1, 2])
        # 同一个naive输入没有明确时区就失败，不能继承机器+8。
        with self.assertRaisesRegex(SourceReadError, '必须声明source_timezone'):
            # 移除时区不改变原数据，其缺项应可读定位。
            list(self.adapter(spec=replace(absolute_spec, timezone=None), signals=(signal,)).iter_batches(self.request(100, ('x',))))
        # 显式Z比source_timezone优先，原offset策略不被覆盖。
        explicit = self.write('explicit.csv', 'time_iso,x\n1970-01-01T00:00:00.000000001Z,1\n')
        # source_timezone仍+8，但Z是输入事实。
        dates = list(self.adapter(spec=replace(absolute_spec, paths=(explicit,)), signals=(signal,)).iter_batches(self.request(100, ('x',))))[0].series['x']
        # 同样精确UTC1ns，不变成负8小时。
        self.assertEqual(dates.time_ns.tolist(), [1])

    def test_empty_projection_seed_and_close(self) -> None:
        """核对空投影/域前观测、并发请求资源和close后拒绝。

        参数: 无；正常两个文件与header-only输入。
        返回: None；不伪造覆盖，不留活动句柄，不删除文件。
        异常: 断言失败表示提前EOF/reset或关闭后继续读取。
        """
        # 请求空投影仍把全部来源读完，实际观测终点明确。
        adapter = self.adapter()
        # 一个合法空批whole-source EOF，不是假样本。
        empty = list(adapter.iter_batches(self.request(1, ())))
        # 时间范围不能从空投影首末猜出；来源原行最后为6s。
        self.assertEqual((len(empty), empty[0].sample_count, empty[0].observed_end_ns), (1, 0, 6_000_000_000))
        # 小窗口仍保留域前原样本，以便后续执行器建立保持状态。
        request = replace(self.request(100, ('current',)), domain_start_ns=2_000_000_000, domain_end_ns=3_000_000_000)
        # 不因窗口小就改变路径顺序或重读旧报文。
        seeded = list(adapter.iter_batches(request))[0].series['current']
        # 0s前置保持与3s真实点都保留，分析层后续按domain限制计算。
        self.assertEqual((seeded.time_ns[0], seeded.time_ns[-1]), (0, 6_000_000_000))
        # 两独立请求真实打开两文件句柄，实例close应释放全部。
        first, second = adapter.iter_batches(self.request()), adapter.iter_batches(self.request())
        # 启动实际读取，不能只测试未启动generator.close。
        next(first), next(second)
        # 两个源读取进度独立，不能隐式共享解码/reader。
        self.assertEqual(len(adapter.handles), 2)
        # close释放当前句柄和generator，反复调用安全。
        adapter.close()
        # 同一个closed实例不能自动重开。
        adapter.close()
        # 真实frame/句柄/活动登记全部释放。
        self.assertEqual((first.gi_frame, second.gi_frame, len(adapter.handles), len(adapter.active)), (None, None, 0, 0))
        # 文件被读取但仍存在，close不删除用户输入。
        self.assertTrue(all(path.exists() for path in self.spec.paths))
        # 静态查询也不绕过生命周期。
        with self.assertRaises(SourceClosedError):
            # 已关闭来源没有新describe。
            adapter.describe()
        # 读取同步入口直接拒绝。
        with self.assertRaises(SourceClosedError):
            # 不延迟到下一次next才失败。
            adapter.iter_batches(self.request())
        # header-only文件没有任何实际时间更新，观测end为unknown。
        header = self.write('header_only.csv', 'time_s,current_mA\n')
        # 只有对应声明字段，空来源不等于schema错误。
        batch = list(self.adapter(spec=replace(self.spec, paths=(header,)), signals=self.signals[1:2]).iter_batches(self.request(1, ('current',))))[0]
        # 不把domain.end=6s伪造为观测充分。
        self.assertEqual((batch.source_eof, batch.sample_count, batch.observed_end_ns), (True, 0, None))

    def test_choices_and_format_declarations(self) -> None:
        """验证显式布尔/枚举编码和文本歧义/格式拒绝。

        参数: 无；声明可区分与不可区分choices。
        返回: None；正常码对应固定域，未知码OUT_OF_RANGE。
        异常: 断言失败表示truthiness或自动猜编码。
        """
        # 显式数值报警码使用bool映射，不把任何非零当True。
        path = self.write('choices.csv', 'time_s,code\n0,1\n1,0\n2,99\n')
        # 当前raw编码选择器与来源声明一致。
        spec = replace(self.spec, paths=(path,))
        # 数值编码到逻辑布尔完全由调用者声明。
        signal = SignalDefinition('alarm', 'table', 'code', SignalDType.BOOL, '1', 10_000_000_000, choices=((1, True), (0, False)))
        # 两后端实际布尔列与质量政策一致。
        for backend in ('reference', 'numpy'):
            # unknown99是已解析原码，而非正常True。
            column = list(self.adapter(backend, spec=spec, signals=(signal,)).iter_batches(self.request(100, ('alarm',))))[0].series['alarm']
            # True和False都是正常逻辑值，第三原码无效。
            np.testing.assert_array_equal(column.values[column.valid], [True, False])
            # 未声明码保留OUT_OF_RANGE而不自动选第一项。
            np.testing.assert_array_equal(column.quality, [0, 0, 16])
        # int1和str1是两个原码，但同CSV文本无法区分，构造必须拒绝。
        ambiguous = SignalDefinition('mode', 'table', 'code', SignalDType.ENUM, '1', 10, choices=((1, 'integer'), ('1', 'text')))
        # 不能只因为SignalDefinition合法就宣称该格式可定位编码。
        with self.assertRaisesRegex(ValueError, '文本歧义'):
            # CSV adapter拒绝歧义，没有增加任意eval/反射。
            self.adapter(spec=spec, signals=(ambiguous,))
        # 非法分隔符/未知unit/错误类型都在静态构造拒绝。
        for changes in ({'delimiter': '||'}, {'unit': 'auto'}, {'paths': str(path)}, {'missing_values': ['', 'NA']}):
            # 不自动sniff或从.csv后缀猜schema。
            with self.assertRaises((TypeError, ValueError)):
                # 错误字段不采用默认替换。
                replace(spec, **changes)

    def test_cleanup_failure_does_not_replace_read_error(self) -> None:
        """同时制造读取与close失败，确认最初根因和清理附注保留。

        参数: 无；work中的坏时间表，真实文件包一层关闭故障。
        返回: None；原ValueError为cause，句柄和登记释放。
        异常: 断言失败表示close错误覆盖最初错误。
        """
        # 错误时间负责最初业务读取失败，文件本身真实打开。
        path = self.write('close_failure.csv', 'time_s,current_mA\nwrong,1000\n')
        # 保存未patch的Path.open，避免mock自己递归。
        original_open = Path.open
        # 故障类只包装真实只读句柄，不改产品解析/数值结果。
        class CloseFailureReader:
            """在真实close之后附加OSError，模拟读句柄清理失败。"""

            def __init__(self, handle) -> None:
                """保存已经真实打开的只读句柄。

                参数: handle为真实TextIO。
                返回: None；不额外读入或写出。
                异常: 无主动异常。
                """
                # 只包装当前测试文件，没有旧模块或全局补丁。
                self.handle = handle

            def __iter__(self):
                """提供真实CSV reader所需的行迭代协议。

                参数: 无；使用当前只读句柄。
                返回: 自身迭代器，不缓存全文件。
                异常: 无主动异常。
                """
                # 数据仍由底层真实文件返回。
                return self

            def __next__(self):
                """读取真实下一行，不注入伪解析结果。

                参数: 无；当前file读取位置。
                返回: str下一行，EOF按StopIteration。
                异常: 底层读取错误原样传播。
                """
                # 解析错误来自真实wrong文本而非mock输出。
                return next(self.handle)

            def close(self) -> None:
                """先关闭真实句柄，再抛可识别的关闭故障。

                参数: 无；当前包装句柄。
                返回: 无正常返回。
                异常: OSError固定测试故障，实际句柄已经关闭。
                """
                # 故障测试也不允许真实资源泄漏。
                self.handle.close()
                # 清理错误应成为附注，不能覆盖最初time解析错误。
                raise OSError('synthetic close failure')

        # 函数替身只用于来源正常文件句柄的清理故障。
        def faulty_open(file_path, *args, **kwargs):
            """真实打开输入并附加close故障层。

            参数: file_path/args/kwargs沿用Path.open原参数。
            返回: 包装真实只读TextIO。
            异常: 原open错误直接传播，测试不更改输入内容。
            """
            # 没有改变旧CAN reader或writer，只包装本新CSV测试路径。
            return CloseFailureReader(original_open(file_path, *args, **kwargs))
        # patch范围只涵盖这一项错误读取，退出即恢复原API。
        with patch.object(Path, 'open', new=faulty_open):
            # 只声明已存在的current字段。
            adapter = self.adapter(spec=replace(self.spec, paths=(path,)), signals=self.signals[1:2])
            # 外层必须报告SourceReadError，不能返回analysis成功。
            with self.assertRaises(SourceReadError) as caught:
                # wrong时间在第一条数据失败，finally随后也close失败。
                list(adapter.iter_batches(self.request(1, ('current',))))
        # 最初cause仍为时间解析ValueError，而不是关闭OSError。
        self.assertIsInstance(caught.exception.__cause__, ValueError)
        # 关闭错误完整记录在原cause附注，不能消失。
        self.assertTrue(any('synthetic close failure' in note for note in caught.exception.__cause__.__notes__))
        # 最初错误之后也没有剩余句柄或请求引用。
        self.assertEqual((len(adapter.handles), len(adapter.active)), (0, 0))


# 独立运行测试有明确入口保护，import不执行文件任务。
if __name__ == '__main__':
    # 所有真实小输入输出在workspace新项目范围。
    unittest.main()
