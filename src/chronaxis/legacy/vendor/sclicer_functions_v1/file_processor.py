import csv
import logging
import os
from datetime import datetime, timedelta
from natsort import natsorted

import can
from utils import ASCReaderForCANFD

# 配置日志
logger = logging.getLogger(__name__)

def iter_frames(path):
    """
    该函数是一个统一的生成器，用于按时间顺序逐个生成 can.Message 对象。
    支持处理单个文件或整个文件夹，具体功能如下：

    1. 当输入为单个文件时：
       - 检查文件扩展名，仅支持 .blf、.asc 和 .csv 格式
       - 若为 .blf 文件，使用 can.BLFReader 读取并生成消息
       - 若为 .asc 文件，使用 can.ASCReader 读取并生成消息
       - 若为 .csv 文件，使用 can.CSVReader 读取并生成消息
       - 若文件格式不支持，抛出 ValueError 异常

    2. 当输入为文件夹时：
       - 筛选出文件夹内所有 .blf、.asc 和 .csv 文件，并按自然排序
       - 递归调用本函数处理每个文件，逐个生成消息

    3. 若输入既不是文件也不是文件夹，抛出 FileNotFoundError 异常

    参数:
    path (str): 输入的文件路径或文件夹路径

    返回:
    generator: 按时间顺序生成 can.Message 对象的生成器

    异常:
    ValueError: 当输入文件的格式不是 .blf、.asc 或 .csv 时抛出
    FileNotFoundError: 当输入路径既不是文件也不是文件夹时抛出
    """
    if os.path.isfile(path):
        ext = os.path.splitext(path)[1].lower()
        if ext == '.blf':
            for m in can.BLFReader(path): yield m
        elif ext == '.asc':
            try:
                for m in can.ASCReader(path,relative_timestamp=False): yield m
            except Exception:
                for m in ASCReaderForCANFD(path, relative_timestamp=False, format_hint='auto'): yield m
        elif ext == '.csv':
            # 使用python-can官方的CSVReader读取CSV文件
            # data需为base64编码
            for m in can.CSVReader(path): yield m
        else:
            raise ValueError("仅支持 blf/asc/csv(data列为base64编码)")
    elif os.path.isdir(path):
        files = natsorted([os.path.join(path, f) for f in os.listdir(path)
                           if f.lower().endswith(('.blf', '.asc', '.csv'))])
        for fp in files:
            for m in iter_frames(fp): yield m
    else:
        raise FileNotFoundError("输入必须是文件或文件夹")


def check_csv_header(file_path):
    """
    前置检查：csv必须含timestamp/arbitration_id/data三列，缺失则抛异常
    参数:
    file_path (str): csv文件路径
    返回:
    bool: 若文件头包含timestamp/arbitration_id/data三列则返回True
    异常:
    ValueError: 当文件头缺失timestamp/arbitration_id/data三列时抛出
    """
    with open(file_path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = [h.lower() for h in next(reader)]
    required = {'timestamp', 'arbitration_id', 'data'}
    miss = required - set(header)
    if miss:
        raise ValueError(f"CSV 缺失列 {miss}")
    return True


def merge_convert(inputs, out_base, out_fmt, db):
    """
    合并输入文件/文件夹→指定格式，csv前置检查
    参数:
    inputs (list): 输入文件/文件夹路径列表
    out_base (str): 输出文件基础名（不含扩展名）
    out_fmt (str): 输出格式，可选"blf"/"asc"/"csv"
    db (can.Database): 数据库对象，用于解析报文
    返回:
    None
    异常:
    ValueError: 当输入文件为csv格式且缺失timestamp/id/data三列时抛出
    FileNotFoundError: 当输入路径既不是文件也不是文件夹时抛出
    """
    from can_processor import build_writer
    
    ext = {"blf": ".blf", "asc": ".asc", "csv": ".csv"}[out_fmt]
    out_path = out_base + ext
    # CSV 前置检查（单文件也检查）
    if out_fmt == "csv":
        for fp in inputs:
            if fp.lower().endswith('.csv'): check_csv_header(fp)

    # 使用build_writer创建统一的写入器
    writer, _ = build_writer(out_path, out_fmt)

    for fp in inputs:
        for msg in iter_frames(fp):
            writer.on_message_received(msg)
    
    # 停止写入器
    writer.stop()
    logger.info(f"合并转换完成→{out_path}")


def output_suffix(path):
    """
    生成带时间戳的输出基础名
    参数:
    path (str): 输入文件路径（不含扩展名）
    返回:
    str: 带时间戳的输出基础名（不含扩展名）
    """
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    base, ext = os.path.splitext(path)
    return base + f"_{ts}"


def fix_asc_header(file_path, utc_offset=0):
    """
    修复ASC文件头部时间信息
    将文件前4行从：
    date Tue Oct 14 16:11:16.648 2025
    base hex  timestamps absolute
    internal events logged
    Begin Triggerblock Tue Jun 10 22:35:34.949 2025
    
    变为：
    date Tue Jun 10 22:35:34.949 2025
    base hex  timestamps absolute
    
    参数:
    file_path (str): ASC文件路径
    utc_offset (int): UTC偏移量(小时)，如果为x，则从date时间减去x小时
    
    返回:
    None
    """
    if not file_path.lower().endswith('.asc'):
        logger.warning(f"{file_path} 不是ASC文件，跳过头部修复")
        return
        
    try:
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        # 查找首行date的时间信息
        header_date_str = None
        if len(lines) > 0 and lines[0].startswith('date '):
            header_date_str = lines[0][len('date '):].strip()
        
        # 查找Begin Triggerblock行，提取时间信息
        trigger_time_str = None
        for line in lines:
            if line.startswith('Begin Triggerblock '):
                trigger_time_str = line[len('Begin Triggerblock '):].strip()
                break
                
        if not trigger_time_str:
            logger.warning(f"在文件{file_path}中未找到Begin Triggerblock行，跳过头部修复")
            return
            
        # 解析时间字符串
        # 时间格式：Tue Jun 10 22:35:34.949 2025
        try:
            trigger_time = datetime.strptime(trigger_time_str, '%a %b %d %H:%M:%S.%f %Y')
            
            # 只有当Begin Triggerblock的时间早于header的date时间时才执行修复
            if header_date_str:
                try:
                    header_date = datetime.strptime(header_date_str, '%a %b %d %H:%M:%S.%f %Y')
                    if trigger_time >= header_date:
                        logger.info(f"Begin Triggerblock时间({trigger_time_str})不早于header的date时间({header_date_str})，无需修复")
                        return
                except ValueError:
                    logger.warning(f"无法解析header的date时间字符串: {header_date_str}，继续修复")
            
            # 应用UTC偏移
            if utc_offset != 0:
                trigger_time = trigger_time - timedelta(hours=utc_offset)
                # 重新格式化时间字符串
                trigger_time_str = trigger_time.strftime('%a %b %d %H:%M:%S.%f')[:-3] + ' ' + str(trigger_time.year)
        except ValueError:
            logger.error(f"无法解析时间字符串: {trigger_time_str}")
            return
            
        # 构建新的文件内容
        new_lines = []
        new_lines.append(f'date {trigger_time_str}\n')
        new_lines.append('base hex  timestamps absolute\n')
        
        # 跳过原始文件的前4行，添加剩余内容
        if len(lines) > 4:
            new_lines.extend(lines[4:])
            
        # 写回文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
            
        logger.info(f"已修复文件头部时间: {file_path}")
        
    except Exception as e:
        logger.error(f"修复ASC文件头部时出错: {str(e)}")