"""检查每批传输了哪些信号样本，以及何时能提交同一时刻的完整更新。

输入是合成内存来源：包含大时间坐标上的1纳秒差、大整数、异步字段、
同刻多次更新和无效观测。输出为手算事实、两后端对照及unittest拒绝断言。
检查类型、列形状、数组所有权和watermark_ns进度；同刻未收齐不能提前
提交，空批也不能重置状态，承诺已完成的时间之后不能再接收同刻晚到样本。
对应T58批次结构和T49核心分组协议；全部数据在内存，不生成临时文件，
不读写RefProjects。CSV文件接入由test_signal_csv.py另外检查。
"""

# 标准测试断言验证业务边界，而不是只镜像数组构造代码。
import unittest
# dataclass替换仅构造明确错误输入，不修改已有冻结对象。
from dataclasses import replace
# patch验证NumPy接线不调用参考归一化，不改变产品实际内核。
from unittest.mock import patch
# NumPy提供真实dtype/shape/掩码输入与严格比较。
import numpy as np

# 显式定义与模型已经在M1验证，不重新猜业务有效期。
from chronaxis.core.binding import SignalDefinition
# 输入与每样本来源身份保持当前会话/字段。
from chronaxis.core.models import MemoryRow, SourceRef, SourceSpec, TimebaseSpec
# 逻辑类型和质量位为全项目统一契约。
from chronaxis.core.types import QualityFlag, SignalDType, TimeType
# 实际公共adapter/类型/validator是当前被测入口。
from chronaxis.sources import BatchValidator, FieldDescription, FieldLocation, MemorySourceAdapter, ReadRequest, SignalBatch, SourceAdapter, SourceClosedError, SourceReadError
# 逐批归一化入口用于构造手算合法或错误协议列。
from chronaxis.sources.packing import pack_decoded


class SourceBatchTests(unittest.TestCase):
    """每测试建立独立合成输入，不共享执行进度或关闭状态。"""

    def setUp(self) -> None:
        """声明真实组、字段、单位及观测域。

        参数: 无额外参数；每测试运行一次。
        返回: None；输入全部内存且冻结。
        异常: 夹具错误应直接失败，不隐藏默认值。
        """
        # 大绝对时间相邻1ns必须保留，不先转float。
        self.start = 2 ** 53
        # 同刻两个current原更新不得在传输层collapse，另含None/Inf/未知枚举。
        rows = (MemoryRow(time_ns=self.start, sequence=0, values={'raw.mA': 10000, 'raw.name': 2 ** 53 + 1, 'raw.mode': 1}),
                MemoryRow(time_ns=self.start, sequence=1, values={'raw.mA': 11000}),
                MemoryRow(time_ns=self.start + 1, sequence=2, values={'raw.mA': None, 'raw.name': 2 ** 64, 'raw.mode': 99}),
                MemoryRow(time_ns=self.start + 2, sequence=3, values={}),
                MemoryRow(time_ns=self.start + 3, sequence=4, values={'raw.mA': float('inf')}),
                MemoryRow(time_ns=self.start + 4, sequence=5, values={'raw.mA': 0, 'raw.mode': 0}))
        # 明确终点在最后真实更新后1ns，不来自推测周期。
        self.source = SourceSpec('table', TimebaseSpec('clock', TimeType.RELATIVE, 'synthetic-batch-v1'), rows,
                                 observation_start_ns=self.start, observation_end_ns=self.start + 5)
        # 单位转换一次，枚举域与标识类型明确。
        self.definitions = (SignalDefinition('current', 'table', 'raw.mA', SignalDType.FLOAT64, 'A', 3, input_unit='mA', scale=.001),
                            SignalDefinition('identifier', 'table', 'raw.name', SignalDType.INT64, '1', 3),
                            SignalDefinition('mode', 'table', 'raw.mode', SignalDType.ENUM, '1', 3, choices=((1, 'scope'), (0, 'off'))))

    def request(self, rows: int = 1, names: tuple[str, ...] = ('current', 'identifier', 'mode')) -> ReadRequest:
        """创建域内请求，保留必须的域前观测与真实终点。

        参数: rows为所有列样本上限；names为显式投影tuple。
        返回: ReadRequest，domain从start+1到start+4。
        异常: 请求模型校验错误传播。
        """
        # 不以请求域裁掉start处前置保持值或补额外周期。
        return ReadRequest('session', names, self.start + 1, self.start + 4, rows)

    def facts(self, batches: list[SignalBatch]) -> dict:
        """收集测试规模内的完整传输事实，生产执行器不这样攒全量。

        参数: batches为当前已读的小夹具批次。
        返回: 别名到时间/序号/有效值/质量/原诊断/ref的列表。
        异常: 结构错误直接失败，不截断。
        """
        # 局部结果只在测试中比较批次切分不变性。
        result = {}
        # 每批按实际异步列还原，不生成混类型宽矩阵。
        for batch in batches:
            # 同一原行多个别名各有自己的样本。
            for name, column in batch.series.items():
                # 逐输出装箱仅用于比较，不执行数值核。
                for index in range(len(column.time_ns)):
                    # enum正常code按该固定域解释，无效占位不用。
                    value = (column.labels[int(column.values[index])] if column.labels else column.values[index].item()) if column.valid[index] else None
                    # 每个字段都属于可追溯结果，整数不经过float。
                    result.setdefault(name, []).append((int(column.time_ns[index]), int(column.sequence[index]), value,
                                                        int(column.quality[index]), column.original_values[index], column.source_ref[index]))
        # 不比较批次编号，它不是业务身份。
        return result

    def test_actual_batches_and_both_backends(self) -> None:
        """验证有限样本传输、完整事实及同刻watermark。

        参数: 无；使用当前合成输入。
        返回: None；手算/两后端/四切分严格一致。
        异常: 断言失败表示协议或数值变化。
        """
        # 第一个实现结果仍必须与独立手算核对，不能只互比。
        baseline = None
        # 两后端和四个合法batch_rows都实际迭代来源。
        for backend in ('reference', 'numpy'):
            # batch1使同一原行与同时间多更新必然跨批。
            for size in (1, 2, 7, 100):
                # 每任务新adapter，不继承之前watermark/绑定。
                adapter = MemorySourceAdapter(self.source, 'session', self.definitions, backend=backend)
                # 实际实现符合公开协议。
                self.assertIsInstance(adapter, SourceAdapter)
                # describe不做数值归一化；最大组可能大于size。
                batches = list(adapter.iter_batches(self.request(size)))
                # 同刻组允许分批，但任何一批不得超过样本总数上限。
                self.assertTrue(all(batch.sample_count <= size for batch in batches))
                # 仅最后整个来源EOF，观测终点保持明确事实。
                self.assertEqual([batch.source_eof for batch in batches], [False] * (len(batches) - 1) + [True])
                # 正常完成后移除活动迭代器，不能每运行留下引用。
                self.assertEqual(len(adapter.active), 0)
                # 真实终点没有根据request.end或最后目标信号猜测。
                self.assertEqual(batches[-1].observed_end_ns, self.start + 5)
                # batch1前四个样本同刻，前三批不能提前承诺组完整。
                if size == 1:
                    # 第四批发出时已经确认下一行更晚，才允许watermark=start。
                    self.assertEqual([batch.watermark_ns for batch in batches[:4]], [None, None, None, self.start])
                # 收集严格事实，非法占位不作为有效数值。
                facts = self.facts(batches)
                # 后端/切分不改变原序号、来源、质量或原诊断。
                if baseline is None:
                    # 保存一次完整测试基线，后续仍有手算断言。
                    baseline = facts
                else:
                    # float10/11/0、Inf诊断和整数在此均精确可比。
                    self.assertEqual(facts, baseline)
                # close幂等且不会删除原输入。
                adapter.close()
        # milliamp额外换算恰好一次，实际invalid覆盖不能改0。
        self.assertEqual([item[2] for item in baseline['current']], [10., 11., None, None, 0.])
        # 缺值/非有限各自原因，有效零仍质量NONE。
        self.assertEqual([item[3] for item in baseline['current']], [0, 0, 1, 8, 0])
        # 大整数正常位值精确保留，超原64位整数明确OVERFLOW。
        self.assertEqual([item[2:4] for item in baseline['identifier']], [(2 ** 53 + 1, 0), (None, 64)])
        # 未声明枚举码99无效，不自动使用首个标签。
        self.assertEqual([item[2:4] for item in baseline['mode']], [('scope', 0), (None, 16), ('off', 0)])

    def test_owned_columns_and_rejected_shapes(self) -> None:
        """验证数组所有权、精确dtype/掩码及结构拒绝。

        参数: 无；从实际转换列构造修改输入。
        返回: None；原数组修改不污染列，非法布局全部拒绝。
        异常: 断言失败表示静默cast/广播或质量错误。
        """
        # 原大整数装箱保持int64，不允许隐式float矩阵。
        series = pack_decoded(self.definitions[1], ((self.start, 0, 2 ** 53 + 1),), SourceRef('session', 'table', 'raw.name'), 'numpy')
        # 外部传入可变数组，构造必须复制。
        values = series.values.copy()
        # 保留所有其他正常声明，避免夹具误报。
        copied = replace(series, values=values)
        # 修改原数组不会反向改变批次。
        values[0] = 1
        # 结果保持原完整位值和27字节存储口径。
        self.assertEqual((copied.values[0], copied.nbytes), (2 ** 53 + 1, 27))
        # 所有owned列只读且不共享调用方值数组。
        self.assertFalse(np.shares_memory(copied.values, values))
        # 普通写入只读输出必须明确失败。
        with self.assertRaises(ValueError):
            # 禁止修改共享结果掩码或整数。
            copied.values[0] = 7
        # 维度/类型/长度/质量/序号分别不能静默修补。
        invalid = ({'time_ns': np.array([self.start], dtype=np.float64)}, {'values': np.ones((1, 1), dtype=np.int64)},
                   {'valid': np.array([], dtype=bool)}, {'quality': np.array([512], dtype=np.uint16)},
                   {'sequence': np.array([-1], dtype=np.int64)}, {'source_ref': ()}, {'original_values': ()})
        # 各错误是独立公共边界，不放宽预期。
        for changes in invalid:
            # 错误类型或形状都属于执行前结构拒绝。
            with self.assertRaises((TypeError, ValueError)):
                # 不使用astype或resize绕过。
                replace(series, **changes)

    def test_watermark_and_empty_batches(self) -> None:
        """核对组未完整、空批承诺、回退/同刻晚到及状态原子性。

        参数: 无；使用current单列投影。
        返回: None；合法同组不同sequence通过，非法承诺拒绝。
        异常: 断言失败表示漏更新/重复结算风险。
        """
        # 独立validator不是已关闭来源复用。
        adapter = MemorySourceAdapter(self.source, 'session', self.definitions)
        # 请求预算允许两原样本，来源描述明确固定类型。
        validator = BatchValidator(adapter.describe(), self.request(2, ('current',)))
        # 局部列构造只用于声明同刻原身份。
        first = pack_decoded(self.definitions[0], ((self.start, 0, 10000),), SourceRef('session', 'table', 'raw.mA'), 'reference')
        # 首批尚未越过完整组，不猜watermark。
        validator.accept(SignalBatch('table', 'session', {'current': first}, None, False, None))
        # 同组不同原序号可以在下一批到达。
        second = replace(first, sequence=np.array([1], dtype=np.int64))
        # 同时间不同观测不会被当作重复丢掉。
        validator.accept(SignalBatch('table', 'session', {'current': second}, None, False, None))
        # 未承诺watermark也必须拒绝来源内真实时间倒退。
        with self.assertRaisesRegex(ValueError, '跨batch时间回退'):
            # 不能借尚未提交时间组的理由重新排序旧更新。
            validator.accept(SignalBatch('table', 'session', {'current': replace(first, time_ns=np.array([self.start - 1], dtype=np.int64))}, None, False, None))
        # 旧序号跨batch重复拒绝，失败不推进watermark。
        with self.assertRaises(ValueError):
            # current@start/seq0已经传送过。
            validator.accept(SignalBatch('table', 'session', {'current': first}, None, False, None))
        # 空batch也可以明确确认完整组，不能reset时间。
        validator.accept(SignalBatch('table', 'session', {}, self.start, False, None))
        # 完整组身份集合立即释放，不攒历史。
        self.assertEqual(validator.pending, {})
        # 已越watermark之后同刻再到必须失败。
        with self.assertRaises(ValueError):
            # 即使新序号也违背完整组保证。
            validator.accept(SignalBatch('table', 'session', {'current': replace(first, sequence=np.array([2], dtype=np.int64))}, self.start, False, None))
        # 空批watermark不能撤销或回退。
        for watermark in (None, self.start - 1):
            # 错误空批不能当作正常无输入略过。
            with self.assertRaises(ValueError):
                # 失败前状态仍是start。
                validator.accept(SignalBatch('table', 'session', {}, watermark, False, None))
        # EOF事实不能替换当前已声明观测范围。
        with self.assertRaisesRegex(ValueError, 'EOF观测终点'):
            # 错误结束不推进ended，后面仍能接受正确EOF。
            validator.accept(SignalBatch('table', 'session', {}, self.start + 4, True, self.start + 4))
        # 最终观测终点与声明一致，whole-source EOF接受。
        validator.accept(SignalBatch('table', 'session', {}, self.start + 4, True, self.start + 5))
        # EOF以后连空批也禁止。
        with self.assertRaises(ValueError):
            # 不能把下一文件当新来源继续此已结束状态。
            validator.accept(SignalBatch('table', 'session', {}, self.start + 5, False, None))

    def test_protocol_binding_limits_and_enum(self) -> None:
        """拒绝列契约变化、错误归属、超批与观测范围回退。

        参数: 无；使用实际adapter的小batch。
        返回: None；每种错误保持当前执行状态独立。
        异常: 断言失败表示输入绑定未核实。
        """
        # 合法description和小batch是错误夹具共同基础。
        adapter = MemorySourceAdapter(self.source, 'session', self.definitions)
        # batch100把合法所有列放一起，方便构造超样本限制。
        batch = list(adapter.iter_batches(self.request(100)))[0]
        # 总行限制按各列样本和，不能只数宽表行。
        with self.assertRaises(ValueError):
            # 此输入实际10个样本，大于1。
            BatchValidator(adapter.describe(), self.request(1)).accept(batch)
        # 错误归属在单批结构先拒绝。
        with self.assertRaises(ValueError):
            # 原SourceRef仍为session，不允许随便换batch session。
            replace(batch, session_id='other')
        # 已知终点不能早于真实数据。
        with self.assertRaises(ValueError):
            # 不通过缩短观测范围隐藏末点。
            replace(batch, observed_end_ns=self.start + 3)
        # enum编码对应的标签域顺序必须稳定。
        mode = replace(batch.series['mode'], labels=('off', 'scope'))
        # 相同dtype但不同域无法证明值含义相同。
        with self.assertRaises(ValueError):
            # 返回列仍数值code合法，跨批契约必须另外拒绝。
            BatchValidator(adapter.describe(), self.request(100)).accept(replace(batch, series={'mode': mode}))
        # 来源时间回退不能靠排序掩盖，即使都是int64。
        with self.assertRaises(ValueError):
            # 当前current列末点改成更早时间，单批先拒绝。
            replace(batch.series['current'], time_ns=np.array([self.start, self.start, self.start + 1, self.start + 3, self.start - 1], dtype=np.int64))

    def test_projection_unknown_range_and_close(self) -> None:
        """核对空投影、unknown范围、请求隔离与迭代资源生命周期。

        参数: 无；当前来源/一个空来源。
        返回: None；未知边界保留，close不删输入且可重复。
        异常: 断言失败表示虚构覆盖或close后仍工作。
        """
        # Unknown的静态范围不能从目标信号首末补成verified。
        unknown = replace(self.source, observation_start_ns=None, observation_end_ns=None)
        # 不提前转换输入，describe是静态元数据。
        adapter = MemorySourceAdapter(unknown, 'session', self.definitions)
        # 未知端点原样保留，实际memory声明也不假装工程核实。
        self.assertEqual((adapter.describe().observation_start_ns, adapter.describe().observation_end_ns, adapter.describe().metadata_status), (None, None, 'declared'))
        # 空投影仍推进来源事实并whole-source EOF，不制造样本。
        batches = list(adapter.iter_batches(self.request(1, ())))
        # end只报告实际最后原行，没有额外1ns周期。
        self.assertEqual((len(batches), batches[0].sample_count, batches[0].observed_end_ns), (1, 0, self.start + 4))
        # 多独立请求的活动登记应由close全部释放。
        first, second = adapter.iter_batches(self.request()), adapter.iter_batches(self.request())
        # 实际启动两个generator，局部批次互不共享。
        next(first), next(second)
        # 明确关闭来源中止两个活动请求。
        adapter.close()
        # 反复close无副作用，原冻结rows保留。
        adapter.close()
        # 生成器frame关闭、登记释放且原输入仍6行。
        self.assertEqual((first.gi_frame, second.gi_frame, len(adapter.active), len(unknown.rows)), (None, None, 0, 6))
        # 关闭后describe/read直接失败，不迟到下一次next才失败。
        with self.assertRaises(SourceClosedError):
            # 生命周期错误不可作为正常元数据返回。
            adapter.describe()
        # 读取错误同样明确。
        with self.assertRaises(SourceClosedError):
            # 不自动重新打开已关闭来源。
            adapter.iter_batches(self.request())
        # 空来源没有观测终点，不能伪造request.end的覆盖。
        empty = MemorySourceAdapter(replace(unknown, rows=()), 'session', self.definitions)
        # EOF允许真正空数据而观测unknown。
        self.assertIsNone(list(empty.iter_batches(self.request()))[-1].observed_end_ns)

    def test_metadata_and_request_errors(self) -> None:
        """验证描述深冻结和请求未知字段/非法预算。

        参数: 无；构造可变嵌套元数据与非法请求。
        返回: None；合法自由JSON键保留，非JSON对象拒绝。
        异常: 断言失败表示结构未保护。
        """
        # 嵌套列表/字典需要深冻结，不能只冻结最外层。
        metadata = {'nested': {'labels': ['original']}}
        # 原字段可含点号，与别名name分开。
        descriptor = FieldDescription('current', FieldLocation('table', 'raw.mA'), SignalDType.FLOAT64, 'A', metadata)
        # 用户修改原元数据不能改变已经公开的说明。
        metadata['nested']['labels'][0] = 'changed'
        # 完整原声明仍存在，内部数组为tuple。
        self.assertEqual(descriptor.metadata['nested']['labels'], ('original',))
        # 自由元数据也不能存任意可执行对象。
        with self.assertRaises(TypeError):
            # 不通过repr或反射转成字符串。
            replace(descriptor, metadata={'bad': object()})
        # enum必须有可核对固定域。
        with self.assertRaises(ValueError):
            # 只有dtype名称不构成完成。
            replace(descriptor, dtype=SignalDType.ENUM)
        # request未知别名和错session在读取前拒绝。
        adapter = MemorySourceAdapter(self.source, 'session', self.definitions)
        # 不能执行后再把所有未知列当正常缺失。
        with self.assertRaises(ValueError):
            # 请求必须属于已描述目录。
            adapter.iter_batches(self.request(names=('unknown',)))
        # 当前实例会话绑定不继承其他请求。
        with self.assertRaises(ValueError):
            # 相同域也不能用另会话定位。
            adapter.iter_batches(replace(self.request(), session_id='other'))
        # 正数限额不接受bool/零/负数，重复投影也拒绝。
        for changes in ({'batch_rows': True}, {'batch_rows': 0}, {'batch_rows': -1}, {'signal_names': ('current', 'current')}):
            # 每错误请求都在静态边界失败。
            with self.assertRaises(ValueError):
                # 不采用静默默认限额或去重。
                replace(self.request(), **changes)

    def test_numpy_normalization_does_not_call_reference(self) -> None:
        """确保实际数组归一化接线独立，非法原值仍有原因。

        参数: 无；显式mA输出列和原raw值tuple。
        返回: None；NumPy转换完成且参考回调未使用。
        异常: 断言或patch错误表示隐藏参考回退。
        """
        # patch只拦被测接线模块的标量入口，数组内核保持真实。
        with patch('chronaxis.sources.packing.normalize_reference', side_effect=AssertionError('hidden reference fallback')):
            # 三同质/缺失原值形成有限列，数值不是逐样本参考循环。
            series = pack_decoded(self.definitions[0], ((self.start, 0, 10000), (self.start + 1, 1, None), (self.start + 2, 2, 0)), SourceRef('session', 'table', 'raw.mA'), 'numpy')
        # 手算10A、UNKNOWN、正常0A完整掩码。
        np.testing.assert_array_equal(series.values[series.valid], [10., 0.])
        # 无效占位不进入上一条值比较；缺值原因明确。
        np.testing.assert_array_equal(series.quality, [0, int(QualityFlag.MISSING), 0])

    def test_read_error_keeps_cause_and_closes_iterator(self) -> None:
        """验证不能装入int64的原序号明确失败并释放活动生成器。

        参数: 无；合法memory逻辑序号超公共数组存储宽度。
        返回: None；SourceReadError含来源，cause保留OverflowError。
        异常: 断言失败表示静默wrap或清理覆盖根因。
        """
        # M1逻辑sequence是非负Python整数，公共数组不能默默wrap超宽身份。
        source = replace(self.source, rows=(MemoryRow(time_ns=self.start, values={'raw.mA': 10000}, sequence=2 ** 64),))
        # 只请求实际存在current字段，不使其他字段缺项掩盖宽度错误。
        adapter = MemorySourceAdapter(source, 'session', self.definitions[:1])
        # typed输入合法但物理布局无法承载，应在读取失败而不是改身份。
        iterator = adapter.iter_batches(self.request(names=('current',)))
        # 保留来源信息，原OverflowError链可定位。
        with self.assertRaisesRegex(SourceReadError, 'table:memory批次失败') as caught:
            # 第一次实际装箱触发明确失败。
            next(iterator)
        # 数值/存储根因不被finally的登记清理替换。
        self.assertIsInstance(caught.exception.__cause__, OverflowError)
        # 失败后不留下活动请求引用或生成器frame。
        self.assertEqual((len(adapter.active), iterator.gi_frame), (0, None))
        # 幂等close继续释放实例，不删除输入。
        adapter.close()


# unittest直接入口保持Windows可独立执行，无导入运行副作用。
if __name__ == '__main__':
    # 执行真实测试，不写旧快照。
    unittest.main()
