"""维护共享资源账本、自有RAM交易槽及未返回owner的有限清理协议。

输入为显式正整数限额及申请bytes，输出为检查后的当前/峰值统计。
RAM申请先校验再分配，释放只能抵销已申请金额；spool保留诊断文件，累计不释放。
AnalysisRunner及执行组件共用账本登记数组nbytes、状态和历史存储费用；它不代表全进程RSS上限。
三个资源事务helper只围绕直接预算调用登记实际归属，或委托真实owner.close，
不创建来源、数组或文件。轻量累计器可复用这些协议，无需加载结果编解码和暂存。
"""

# 明确超限异常，首版不降采样、丢结果或偷改窗口。
from .errors import BudgetExceededError


def _reserve_owned_ram(owner, amount: int, slot: str) -> None:
    """预约一笔RAM并按实际账本登记owner及指定槽位，覆盖成功后取消。

    参数: owner已初始化_budget/_held_cost/slot；amount为bytes；slot为实际费用字段。
    返回: None。异常: 原预算/取消传播，未实际入账不增加自有费用。
    边界: 仅围绕一次单线程直接预算调用判断，不用子操作后的总额猜测借用费用。
    """
    # 预算回调可能先更新再抛异常，finally必须登记已成功的这一笔申请。
    before = owner._budget.ram_bytes
    try:
        owner._budget.reserve_ram(amount)
    finally:
        if owner._budget.ram_bytes == before + amount:
            owner._held_cost += amount
            setattr(owner, slot, getattr(owner, slot) + amount)


def _release_owned_ram(owner, amount: int, slot: str) -> None:
    """抵销一笔实际自有RAM，释放前取消保留金额，释放后取消立即清账。

    参数: owner持有实际_budget/_held_cost/slot；amount为bytes；slot为对应实际费用。
    返回: None。异常: 原预算/取消传播，恢复后不得重复抵销已释放金额。
    """
    # 空槽不调用外部预算回调，也不把未付金额用于抵销其他owner的费用。
    if amount == 0:
        return
    before = owner._budget.ram_bytes
    try:
        owner._budget.release_ram(amount)
    finally:
        if owner._budget.ram_bytes == before - amount:
            owner._held_cost -= amount
            setattr(owner, slot, getattr(owner, slot) - amount)


def _cleanup_owner(owner, exc: BaseException, attribute: str, label: str) -> None:
    """尝试关闭构造未返回的真实owner，持续失败将恢复句柄附在原异常。

    参数: owner为实际部分构造对象；exc为原异常；attribute为恢复属性名；label为说明。
    返回: None，不覆盖原异常。异常: 关闭错误记录在原异常notes中，不向外替换它。
    """
    # 至多两次处理瞬时关闭取消；持续故障保留原对象，调用方恢复后显式close。
    for attempt in range(2):
        try:
            owner.close()
            break
        except BaseException as cleanup:
            exc.add_note(f'{label}清理第{attempt + 1}次失败: {type(cleanup).__name__}')
    if not (getattr(owner, '_closed', False) or getattr(owner, 'closed', False)):
        setattr(exc, attribute, owner)
        exc.add_note(f'释放恢复后调用{attribute}.close()')


class ResourceBudget:
    """保存限额与单线程共享计数；每次申请失败都保持原计数不变。"""

    def __init__(self, memory_budget_bytes: int = 268435456, spool_quota_bytes: int | None = None):
        """校验并初始化资源计数，不分配数组或创建文件。

        参数: memory_budget_bytes为RAM估算bytes；spool_quota_bytes为可选累计限额。
        返回: 新账本。异常: ValueError为bool、非正数或非原生int。
        """
        # 配置从计划传入也重新校验，不能把None磁盘配额解释为无限物理磁盘。
        for value in (memory_budget_bytes, spool_quota_bytes):
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError('资源限额需要正原生int')
        if memory_budget_bytes is None:
            raise ValueError('RAM限额不能省略')
        self.memory_budget_bytes = memory_budget_bytes
        self.spool_quota_bytes = spool_quota_bytes
        self.ram_bytes = self.peak_ram_bytes = self.spool_bytes = 0

    def reserve_ram(self, amount: int) -> None:
        """在分配前保守申请新层RAM，失败不修改账本。

        参数: amount为非负原生int bytes。返回: None。
        异常: ValueError为金额错误；BudgetExceededError为超限。
        """
        # 使用Python整数避免账本定宽溢出。
        self._amount(amount)
        if self.ram_bytes + amount > self.memory_budget_bytes:
            raise BudgetExceededError(f'新分析层RAM估算超限: {self.ram_bytes}+{amount}>{self.memory_budget_bytes}')
        self.ram_bytes += amount
        self.peak_ram_bytes = max(self.peak_ram_bytes, self.ram_bytes)

    def release_ram(self, amount: int) -> None:
        """释放已有申请，不能凭负数或重复释放隐藏状态开销。

        参数: amount为非负原生int bytes。返回: None。
        异常: ValueError为金额错误或超出当前申请。
        """
        self._amount(amount)
        if amount > self.ram_bytes:
            raise ValueError('RAM释放超出当前申请')
        self.ram_bytes -= amount

    def reserve_spool(self, amount: int) -> None:
        """写入前累计申请磁盘量，失败或部分写入也保守保留申请。

        参数: amount为非负原生int bytes。返回: None。
        异常: ValueError为金额错误；BudgetExceededError为累计超配额。
        """
        self._amount(amount)
        if self.spool_quota_bytes is not None and self.spool_bytes + amount > self.spool_quota_bytes:
            raise BudgetExceededError('累计磁盘暂存超过spool_quota_bytes')
        self.spool_bytes += amount

    @staticmethod
    def _amount(amount: int) -> None:
        """检查金额，防止布尔和负数影响预算。

        参数: amount为申请金额。返回: None。异常: ValueError为非法金额。
        """
        if type(amount) is not int or amount < 0:
            raise ValueError('资源金额需要非负原生int')

    def snapshot(self) -> dict:
        """返回独立的小型资源快照，不修改计数。

        参数: 无。返回: 限额、当前/峰值RAM估算和累计spool预留。
        异常: 无；整进程RSS不在此模型内。
        """
        return {'memory_budget_bytes': self.memory_budget_bytes, 'spool_quota_bytes': self.spool_quota_bytes,
                'ram_estimated_bytes': self.ram_bytes, 'peak_ram_estimated_bytes': self.peak_ram_bytes,
                'spool_reserved_bytes': self.spool_bytes, 'whole_process_rss': 'not_measured'}
