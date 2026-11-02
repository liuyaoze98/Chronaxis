"""在读取器已有预算内同步交付必要消息，不建立额外历史或结果副本。"""

from ..results.budget import _reserve_owned_ram, _release_owned_ram
from .history import _metadata_bytes


def deliver_message(owner, projection, consumer, frame, sequence, values, time_ns, *, canonical_keys=False):
    """先付本次投影费用，再同步调用消费者，返回后释放临时消息。

    参数: owner为拥有_update_cost槽的读取器；projection为有限CAN投影；
        consumer为同步可调用对象；其余为当前原帧、序号、已解码值及实际时间。
        canonical_keys说明文本入口的规范字段键。消费者如需保留对象，须自行
        取得保存费用；此调用只借出当前对象，不承诺历史生命周期。
    返回: None，非目标帧不构造消息。异常: 预算/值/消费者及清理错误原样传播。
    """
    fields = projection.fields_for(frame)
    if not projection.accepts_frame(frame):
        return
    update = None
    # 费用只取所选字段；无关解码值不遍历、不复制进计算输入。
    cost = 16384 + sum(1024 + 16 * _metadata_bytes(values.get(
        field.key if canonical_keys else field.signal)) for field in fields)
    _reserve_owned_ram(owner, cost, '_update_cost')
    try:
        update = projection.build(frame, sequence, values, time_ns, canonical_keys=canonical_keys)
        consumer(update)
    except BaseException as error:
        update = None
        try:
            _release_owned_ram(owner, owner._update_cost, '_update_cost')
        except BaseException as cleanup:
            # 原消费者错误优先；尚未释放的费用留在同一read槽，供外层关闭重试。
            error.add_note('消息投影费用清理失败：' + type(cleanup).__name__)
        raise
    else:
        update = None
        _release_owned_ram(owner, owner._update_cost, '_update_cost')
