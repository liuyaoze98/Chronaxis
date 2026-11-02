import ast
import logging

import can
import cantools

# 配置日志
logger = logging.getLogger(__name__)


def build_writer(out_path, out_fmt):
    """
    根据指定的输出格式和路径，创建对应的 CAN 数据写入器。

    该函数支持三种输出格式：
    - 'blf'：使用 can.BLFWriter 写入 BLF 格式文件
    - 'asc'：使用 can.ASCWriter 写入 ASC 格式文件
    - 'csv'：使用 can.CSVWriter 写入 CSV 格式文件

    参数:
    out_path (str): 输出文件的路径
    out_fmt (str): 输出文件的格式，支持 'blf'、'asc'、'csv'

    返回:
    tuple: 一个包含写入器和路径的元组 (writer, out_path)
    """
    if out_fmt == "blf":
        return can.BLFWriter(out_path), out_path
    elif out_fmt == "asc":
        return can.ASCWriter(out_path), out_path
    elif out_fmt == "csv":
        # 使用python-can官方的CSVWriter
        return can.CSVWriter(out_path), out_path
    else:
        raise ValueError("format 必须是 blf/asc/csv")


def eval_expr(expr, sig_dict):
    """
    解析并评估一个表达式，该表达式使用信号字典中的信号值。

    该函数会先对输入的表达式进行语法检查，确保只包含允许的语法节点。
    接着检查表达式中引用的信号是否都存在于信号字典中，如果有缺失则返回 False。
    最后使用安全的方式评估表达式，若评估过程中出现异常也返回 False。
    对于浮点数比较，使用近似比较来解决精度问题。

    参数:
    expr (str): 需要解析和评估的表达式字符串
    sig_dict (dict): 信号字典，键为信号名，值为信号值

    返回:
    bool: 若表达式评估结果为真则返回 True；若表达式语法非法、引用缺失信号或评估出错，返回 False
    """
    try:
        # 定义允许的语法节点集合，限制表达式使用的语法
        allowed = {ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
                   ast.And, ast.Or, ast.Module, ast.Expr, ast.Expression,
                   ast.Compare, ast.BinOp, ast.Name, ast.Load, ast.Constant}
        # 将表达式解析为抽象语法树节点
        node = ast.parse(expr, mode='eval')
        # 遍历语法树节点，检查是否存在非法语法
        for n in ast.walk(node):
            if type(n) not in allowed:
                raise ValueError(f"非法语法：{type(n)}")
        # 缺失信号直接返回 False
        for name in ast.walk(node):
            if isinstance(name, ast.Name) and name.id not in sig_dict:
                return False
        
        # 处理浮点数精度问题：对信号字典中的浮点数进行四舍五入处理
        # 保留足够的小数位数以保持精度，同时消除精度误差
        processed_sig_dict = {}
        for k, v in sig_dict.items():
            if isinstance(v, float):
                # 保留10位小数，足够精确且能消除大部分精度误差
                processed_sig_dict[k] = round(v, 10)
            else:
                processed_sig_dict[k] = v
        
        # 筛选出信号字典中数值类型或布尔类型的值，构建评估环境
        env = {k: v for k, v in processed_sig_dict.items() if isinstance(v, (int, float, bool))}
        logger.debug(f"原始信号字典：{sig_dict}")
        logger.debug(f"处理后信号字典：{processed_sig_dict}")
        # 编译并评估表达式
        return eval(compile(node, '<string>', 'eval'), {"__builtins__": {}}, env)
    except Exception as e:
        logger.debug("eval_expr 异常：%s", e)
        return False


def parse_frame(msg, db):
    """
    从单帧CAN报文解析出全部信号值。

    该函数尝试使用提供的数据库对象解码CAN报文，
    解析出报文中包含的所有信号及其对应的值。
    如果解析失败，返回空字典。

    参数:
    msg (can.Message): CAN报文对象，包含报文ID和数据
    db (can.Database): CAN数据库对象，用于信号解码

    返回:
    dict: 包含信号名和对应值的字典；如果解析失败，返回空字典

    异常:
    无显式异常抛出，所有异常都会被捕获并返回空字典
    """
    try:
        vals = db.decode_message(msg.arbitration_id, msg.data, decode_choices=False, allow_truncated=True)
        return vals
    except Exception:
        return {}


def get_signals_for_message_id(db, message_id):
    """
    获取指定CAN报文ID包含的所有信号名称。

    该函数从数据库中查找指定ID的CAN报文定义，
    并返回该报文中包含的所有信号名称集合。
    如果未找到对应报文，返回空集合。

    参数:
    db (can.Database): CAN数据库对象，包含报文和信号定义
    message_id (int): CAN报文ID

    返回:
    set: 包含信号名称的集合；如果未找到报文，返回空集合

    异常:
    无显式异常抛出，所有异常都会被捕获并返回空集合
    """
    try:
        message = db.get_message_by_frame_id(message_id)
        return {signal.name for signal in message.signals}
    except:
        return set()