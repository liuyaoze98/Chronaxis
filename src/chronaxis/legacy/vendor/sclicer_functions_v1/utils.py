import logging
import os
import re
import can
from typing import Generator, List, Dict, Any, Optional, Tuple
from datetime import datetime

# 配置日志
logger = logging.getLogger(__name__)

class ASCReaderForCANFD:
    """
    通用CAN FD ASC文件解析器
    支持多种格式的CAN FD ASC文件，自动适应不同的数据布局
    生成与python-can兼容的Message对象
    """
    
    def __init__(self, file_path: str, relative_timestamp: bool = False, format_hint: str = 'auto'):
        """
        初始化解析器
        
        参数:
        file_path: ASC文件路径
        relative_timestamp: 是否使用相对时间戳
        format_hint: 格式提示，可选值：'auto'（自动检测）、'standard'（标准格式）、'custom'（自定义格式）
        """
        self.file_path = file_path
        self.relative_timestamp = relative_timestamp
        self.first_timestamp = None
        self.format_hint = format_hint
        
        # 根据格式提示选择初始正则表达式
        self.patterns = self._initialize_patterns()
        self.selected_pattern = None
        self.selected_pattern_index = -1
        # 头部时间戳策略：absolute/relative/unknown；基准日期时间（epoch秒）
        self.timestamps_mode: str = 'unknown'
        self.base_epoch: Optional[float] = None
        
        # 如果是自动模式，需要进行格式检测
        if format_hint == 'auto' and os.path.exists(self.file_path):
            self._detect_format()
        # 解析头部，获取日期与时间戳模式
        self._parse_header()

    def _initialize_patterns(self) -> List[re.Pattern]:
        """
        初始化支持的多种正则表达式模式
        """
        patterns = []
        
        # 模式1: 当前使用的格式 - CANFD 后跟多个字段
        patterns.append(re.compile(r'^([\d\.]+)\s+CANFD\s+(\d+)\s+([\da-fA-F]+)\s+(\w+)\s+(\d+)\s+(\d+)\s+(\w+)\s+(\d+)\s+(\d+)\s+(.*)$'))
        
        # 模式2: 简化的格式 - 时间戳 CANFD 通道 ID 方向 数据
        patterns.append(re.compile(r'^([\d\.]+)\s+CANFD\s+(\d+)\s+([\da-fA-F]+)\s+(\w+)\s+(.*)$'))
        
        # 模式3: 可能的其他格式变体
        patterns.append(re.compile(r'^([\d\.]+)\s+CANFD\s+(\d+)\s+([\da-fA-F]+)\s+(\w+)\s+(\d+)\s+(.*)$'))
        
        # 模式4: 更通用的格式，尝试匹配各种可能的CAN FD格式
        patterns.append(re.compile(r'^([\d\.]+)\s+CANFD\s+.*?([\da-fA-F]+)\s+(\w+)\s+.*?(\d+)\s+(.*)$'))
        
        # 模式5: 无CANFD关键字的格式 - 时间戳 通道 ID 方向 [其他字段] 数据
        patterns.append(re.compile(r'^([\d\.]+)\s+(\d+)\s+([\da-fA-F]+)\s+(\w+)\s+(.*)$'))
        
        # 模式6: 专门用于用户提供的新格式 - 匹配 0.001990 1 1ac Rx 1 0 d 8 8 66 03 e2 97 76 7d 14 16 这样的格式
        patterns.append(re.compile(r'^([\d\.]+)\s+(\d+)\s+([\da-fA-F]+)\s+(\w+)\s+(\d+)\s+(\d+)\s+(\w+)\s+(\d+)\s+(.*)$'))
        
        return patterns

    def _detect_format(self):
        """
        自动检测ASC文件的格式
        """
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or line.startswith('//') or line.startswith('date') or line.startswith('base'):
                        continue
                    
                    # 尝试每种模式
                    for i, pattern in enumerate(self.patterns):
                        match = pattern.match(line)
                        if match:
                            self.selected_pattern = pattern
                            self.selected_pattern_index = i
                            # 记录匹配的组信息，用于后续解析
                            self._record_pattern_info(match)
                            return
        except Exception:
            # 静默失败
            pass

    def _record_pattern_info(self, match: re.Match):
        """
        记录匹配模式的信息，用于后续解析
        """
        # 这里可以记录更多关于匹配模式的信息
        self.match_group_count = len(match.groups())
    
    def __iter__(self) -> Generator[can.Message, None, None]:
        """
        迭代器接口，生成can.Message对象
        """
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"文件 {self.file_path} 不存在")
        
        with open(self.file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过注释和文件头
                if not line or line.startswith('#') or line.startswith('//') or line.startswith('date') or line.startswith('base'):
                    continue
                
                message = self._parse_line(line)
                if message:
                    yield message

    def _parse_line(self, line: str) -> Optional[can.Message]:
        """
        解析单行CAN FD报文，尝试多种格式
        
        参数:
        line: 单行CAN FD报文数据
        
        返回:
        can.Message: 解析后的CAN消息对象，解析失败返回None
        """
        # 如果已经选择了模式，先尝试使用该模式
        if self.selected_pattern:
            message = self._parse_with_pattern(line, self.selected_pattern)
            if message:
                return message
        
        # 如果没有选择模式或当前模式失败，尝试所有模式
        for pattern in self.patterns:
            message = self._parse_with_pattern(line, pattern)
            if message:
                # 更新选择的模式以提高后续解析效率
                if self.selected_pattern is None:
                    self.selected_pattern = pattern
                return message
        
        # 如果所有模式都失败，尝试基于空格分割的通用解析
        return self._parse_with_generic_split(line)

    def _parse_with_pattern(self, line: str, pattern: re.Pattern) -> Optional[can.Message]:
        """
        使用指定的正则表达式模式解析行
        """
        match = pattern.match(line)
        if not match:
            return None
        
        try:
            groups = match.groups()
            # 提取时间戳（通常是第一个组）
            timestamp = float(groups[0])
            # 应用头部时间策略
            timestamp = self._apply_header_timestamp(timestamp)
            
            # 尝试找到ID、通道和数据字段
            channel = 1  # 默认通道
            arbitration_id_hex = None
            data_bytes_str = None
            
            # 根据不同模式的组数量处理
            if len(groups) >= 10:  # 模式1
                channel = int(groups[1])
                arbitration_id_hex = groups[2]
                data_bytes_str = groups[9]
            elif len(groups) >= 5 and len(groups) < 6:  # 模式2
                channel = int(groups[1])
                arbitration_id_hex = groups[2]
                data_bytes_str = groups[4]
            elif len(groups) >= 6 and len(groups) < 9:  # 模式3或模式5
                channel = int(groups[1])
                arbitration_id_hex = groups[2]
                data_bytes_str = groups[5]
            elif len(groups) >= 9:  # 模式6 (用户提供的新格式)
                channel = int(groups[1])
                arbitration_id_hex = groups[2]
                # 在模式6中，数据部分从第8个组开始
                data_bytes_str = groups[8]
            else:  # 模式4或其他情况
                # 尝试在各组中找到有效的ID
                for i in range(1, len(groups)):
                    if re.match(r'^[\da-fA-F]+$', groups[i]) and len(groups[i]) > 0:
                        arbitration_id_hex = groups[i]
                        break
                # 数据通常在最后一个组
                data_bytes_str = groups[-1]
            
            # 如果找不到必要的字段，返回None
            if not arbitration_id_hex or not data_bytes_str:
                return None
            
            # 处理相对时间戳
            if self.relative_timestamp:
                if self.first_timestamp is None:
                    self.first_timestamp = timestamp
                timestamp -= self.first_timestamp
            
            # 解析arbitration_id
            arbitration_id = int(arbitration_id_hex, 16)
            
            # 判断是否为扩展ID
            is_extended_id = arbitration_id > 0x7FF
            
            # 解析数据字节
            data_bytes = []
            for byte_str in data_bytes_str.split():
                try:
                    # 跳过非十六进制值
                    if re.match(r'^[\da-fA-F]+$', byte_str):
                        data_bytes.append(int(byte_str, 16))
                except ValueError:
                    continue
            
            # 创建can.Message对象
            message = can.Message(
                timestamp=timestamp,
                arbitration_id=arbitration_id,
                is_extended_id=is_extended_id,
                data=data_bytes,
                channel=channel,
                is_remote_frame=False,
                is_error_frame=False
            )
            
            return message
            
        except Exception:
            # 解析错误时静默失败，尝试其他模式
            return None

    def _parse_with_generic_split(self, line: str) -> Optional[can.Message]:
        """
        基于空格分割的通用解析方法，作为最后的尝试
        增强点：
        - 支持以"*"开头的行（星号前缀）
        - 支持时分秒时间戳 "HH:MM:SS.mmm"
        - 支持日期+时间前缀 "YYYY.MM.DD HH:MM:SS.mmm"
        - 兼容有/无 CANFD 关键字
        """
        try:
            raw = line.strip()
            if not raw:
                return None

            parts = raw.split()
            if len(parts) < 3:
                return None

            idx = 0

            # 1) 跳过星号前缀
            if parts[idx] == '*':
                idx += 1
                if idx >= len(parts):
                    return None

            # 2) 解析时间戳（支持三种变体）
            timestamp: Optional[float] = None
            hms_token: Optional[str] = None

            # 情形A：日期+时间
            if re.match(r'^\d{4}\.\d{2}\.\d{2}$', parts[idx]) and (idx + 1) < len(parts) and re.match(r'^\d{1,2}:\d{2}:\d{2}\.\d+$', parts[idx + 1]):
                hms_token = parts[idx + 1]
                idx += 2
            # 情形B：时分秒时间戳
            elif re.match(r'^\d{1,2}:\d{2}:\d{2}\.\d+$', parts[idx]):
                hms_token = parts[idx]
                idx += 1
            else:
                # 情形C：普通浮点秒
                try:
                    timestamp = float(parts[idx])
                    idx += 1
                except ValueError:
                    return None

            # 如果是时分秒形式，转换为秒
            if timestamp is None and hms_token:
                try:
                    hh, mm, ss = hms_token.split(':')
                    timestamp = int(hh) * 3600 + int(mm) * 60 + float(ss)
                except Exception:
                    return None

            # 3) 可选的 CANFD 关键字
            if idx < len(parts) and parts[idx].upper() == 'CANFD':
                idx += 1

            # 4) 通道（优先取当前位置的整数，必要时向前扫描）
            if idx >= len(parts):
                return None
            try:
                channel = int(parts[idx])
                idx += 1
            except ValueError:
                found_channel = False
                for j in range(idx, min(idx + 4, len(parts))):
                    try:
                        channel = int(parts[j])
                        idx = j + 1
                        found_channel = True
                        break
                    except ValueError:
                        continue
                if not found_channel:
                    return None

            # 5) ID：从当前位置起，第一个纯十六进制token
            arbitration_id_hex = None
            id_index = -1
            for j in range(idx, len(parts)):
                if re.match(r'^[\da-fA-F]+$', parts[j]):
                    arbitration_id_hex = parts[j]
                    id_index = j
                    # 跳过方向标识
                    if j + 1 < len(parts) and parts[j + 1].upper() in ('RX', 'TX'):
                        j += 1
                    break
            if not arbitration_id_hex:
                return None

            # 6) 数据起始位置：优先从末尾向前找到连续的字节
            data_start_index = -1
            for k in range(len(parts) - 1, id_index, -1):
                if re.match(r'^[\da-fA-F]{1,2}$', parts[k]):
                    t = k
                    while t > id_index and re.match(r'^[\da-fA-F]{1,2}$', parts[t]):
                        t -= 1
                    data_start_index = t + 1
                    break
            if data_start_index == -1:
                # 前向查找，跳过常见标志
                data_start_index = id_index + 1
                while data_start_index < len(parts) and (
                    parts[data_start_index].upper() in ('RX', 'TX', 'FD', 'BRS', 'ESI', 'TRIGGER') or
                    parts[data_start_index].upper().startswith('DLC')
                ):
                    data_start_index += 1

            # 7) 解析数据字节
            data_bytes = []
            for tkn in parts[data_start_index:]:
                if re.match(r'^[\da-fA-F]{1,2}$', tkn):
                    try:
                        data_bytes.append(int(tkn, 16))
                    except ValueError:
                        pass

            # 8) 相对时间戳处理
            if self.relative_timestamp:
                if self.first_timestamp is None:
                    self.first_timestamp = timestamp
                timestamp -= self.first_timestamp

            # 9) 组装消息
            arbitration_id = int(arbitration_id_hex, 16)
            is_extended_id = arbitration_id > 0x7FF
            message = can.Message(
                timestamp=timestamp,
                arbitration_id=arbitration_id,
                is_extended_id=is_extended_id,
                data=data_bytes,
                channel=channel,
                is_remote_frame=False,
                is_error_frame=False
            )
            return message
        except Exception:
            return None

    def add_custom_pattern(self, pattern: str) -> bool:
        """
        添加自定义正则表达式模式
        
        参数:
        pattern: 正则表达式字符串
        
        返回:
        bool: 添加是否成功
        """
        try:
            compiled_pattern = re.compile(pattern)
            self.patterns.append(compiled_pattern)
            # 重置选择的模式，以便下次解析时重新尝试
            self.selected_pattern = None
            return True
        except re.error:
            return False

    def _parse_header(self) -> None:
        """解析文件头的日期与时间戳模式，使行为与 can.ASCReader 保持一致"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    s = line.strip()
                    if not s:
                        continue
                    # 识别 timestamps 模式
                    if s.lower().startswith('base') and 'timestamps' in s.lower():
                        if 'absolute' in s.lower():
                            self.timestamps_mode = 'absolute'
                        elif 'relative' in s.lower():
                            self.timestamps_mode = 'relative'
                        continue
                    # 识别两类日期格式
                    if s.lower().startswith('date'):
                        # 格式1：date YYYY.MM.DD time HH:MM:SS.mmm
                        m1 = re.match(r'^date\s+(\d{4})\.(\d{2})\.(\d{2})\s+time\s+(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?$', s)
                        if m1:
                            y, mo, d, hh, mm, ss, ms = m1.groups()
                            ms = int(ms) if ms else 0
                            dt = datetime(int(y), int(mo), int(d), int(hh), int(mm), int(ss), ms*1000)
                            self.base_epoch = dt.timestamp()
                            continue
                        # 格式2：date Tue Sep 03 10:39:01 AM 2024
                        try:
                            text = s[5:].strip()  # 去掉前缀 'date '
                            dt = datetime.strptime(text, '%a %b %d %I:%M:%S %p %Y')
                            self.base_epoch = dt.timestamp()
                        except Exception:
                            pass
                        continue
                    # 遇到可能的数据行，停止头部解析
                    if re.match(r'^[\*\d]', s):
                        break
        except Exception:
            # 头部解析失败不影响后续解析
            pass

    def _apply_header_timestamp(self, ts: float) -> float:
        """根据头部策略调整时间戳：absolute 时叠加基准（若存在），relative 保持原值"""
        try:
            if self.timestamps_mode == 'absolute' and self.base_epoch is not None:
                return self.base_epoch + ts
            return ts
        except Exception:
            return ts

__all__ = ['ASCReaderForCANFD']
