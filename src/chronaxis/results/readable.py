"""将结果流关联成可直接阅读的CSV，不重新读取或计算输入。

事件、窗口及计算的既有排序不同，先用临时SQLite索引关联，再逐行发布。
索引只有本次结果，固定缓存、禁止mmap、写前预付页面；关闭后删除，不发布
原表副本。CSV、JSONL旧路径不调用本模块。所有权保存在AnalysisResult供失败恢复。
"""

# SQLite属于Python标准库；只创建本次发布目录中的私有临时文件。
import csv
import hashlib
import json
import sqlite3
from contextlib import closing
from math import ceil
from .budget import _reserve_owned_ram, _release_owned_ram
from .errors import ResultFormatError
from .summary import summary_fields
from .readable_format import STATES, REASONS, seconds, explanation, quality_text

IDENTITY = ('dataset_id', 'entity_id', 'session_id')
LABELS = ('数据集', '对象', '会话')
FILES = {'events': '事件结果.csv', 'segments': '窗口结果.csv', 'calculations': '会话结果.csv',
         'sequences': '配对结果.csv', 'selections': '选择结果.csv', 'aggregations':'聚合结果.csv',
         'contributions': '贡献明细.csv', 'input_trace': '输入追溯.csv'}


def _json(value):
    """编码临时索引值。参数: 平坦字段。返回: JSON文本。异常: 非有限值拒绝。"""
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


class ReadableWriter:
    """拥有单次发布的关联索引及有限列定义；close可重试，不拥有输入或正式结果。"""

    def __init__(self, owner, directory, iterator_factory):
        """仅安装可恢复字段，资源在prepare取得。

        参数: owner为AnalysisResult，directory为本次临时目录，iterator_factory为结果游标。
        返回: 未准备的writer。异常: 无文件副作用。
        """
        self.owner, self.directory, self.iterator_factory = owner, directory, iterator_factory
        self.path = directory / '.readable-index.sqlite'
        self.connection = None
        self._budget = owner.spool.budget
        self._held_cost = self._ram_cost = 0
        self.pages = 0
        self.closed = False
        self.metrics = {'session': {}, 'event': {}, 'segment': {}}
        self.counts, self.infos = {}, {}
        self.confirmation = False
        self.quality_handle = None
        self.coverage = None

    def _execute(self, sql, values=(), size=0):
        """写前预留SQLite页面，上限由数据库本身强制执行。

        参数: sql/values为受控语句，size为本条JSON字符数。返回: cursor。
        异常: 配额、SQL、IO或取消传播。预留包含B树分裂余量，不按总行数预占RAM。
        """
        # page_count包含事务中已分配页；保守覆盖UTF8值、索引键及B树分裂。
        count = self.connection.execute('PRAGMA page_count').fetchone()[0]
        needed = count + 16 + ceil(size * 12 / 4096)
        if needed > self.pages:
            self._budget.reserve_spool((needed - self.pages) * 4096)
            self.pages = needed
            self.connection.execute(f'PRAGMA max_page_count={needed}')
        return self.connection.execute(sql, values)

    def _rows(self, table):
        """按原游标逐条读已计算结果，保持严格解析和真实关闭。

        参数: table为启用表。返回: 平坦字段生成器。异常: 读取/校验/关闭错误传播。
        """
        with closing(self.iterator_factory(self.owner, table)) as iterator:
            count = 0
            for row in iterator:
                count += 1
                fields = summary_fields(row)
                # 显式质量诊断仍随唯一必要读取得到，不另扫一遍结果。
                if self.quality_handle is not None:
                    state_field = {'selections': 'selection', 'contributions': 'reason',
                                   'input_trace': 'record_type'}.get(table, 'status')
                    key = table + ':' + fields[state_field]
                    self.coverage[key] = self.coverage.get(key, 0) + 1
                    diagnostic = {key: fields[key] for key in ('sequence', *IDENTITY, 'quality', state_field)}
                    diagnostic['table'] = table
                    self.quality_handle.write(_json(diagnostic) + '\n')
                yield fields
            if count != self.owner.spool.counts.get(table, 0):
                raise ResultFormatError('可读导出行数与暂存不一致')

    def prepare(self):
        """建立必要关联和列定义，不读取原始日志。

        参数: 无。返回: None。异常: 重复身份、重复指标、配额/IO传播。
        """
        if not any(self.owner.spool.counts.get(table, 0) for table in ('events', 'segments', 'sequences', 'calculations')):
            # 只有逐条明细或全空结果时没有关联消费者，连空索引也不创建。
            self.confirmation = True
            return
        _reserve_owned_ram(self, 262144, '_ram_cost')
        # 禁止系统临时排序文件和mmap；后续查询只走已声明索引。
        self._budget.reserve_spool(65536)
        self.pages = 16
        self.connection = sqlite3.connect(self.path, isolation_level=None)
        self.connection.execute('PRAGMA page_size=4096')
        self.connection.execute('PRAGMA max_page_count=16')
        self.connection.execute('PRAGMA cache_size=-64')
        self.connection.execute('PRAGMA mmap_size=0')
        self.connection.execute('PRAGMA journal_mode=OFF')
        self.connection.execute('PRAGMA synchronous=OFF')
        self.connection.execute('PRAGMA temp_store=MEMORY')
        self._execute('CREATE TABLE objects(kind TEXT,d TEXT,e TEXT,s TEXT,id TEXT,n INTEGER,payload TEXT,'
                      'PRIMARY KEY(kind,d,e,s,id),UNIQUE(kind,n)) WITHOUT ROWID')
        self._execute('CREATE TABLE metrics(d TEXT,e TEXT,s TEXT,scope TEXT,parent TEXT,name TEXT,payload TEXT,'
                      'PRIMARY KEY(d,e,s,scope,parent,name)) WITHOUT ROWID')
        self.connection.execute('BEGIN')
        # 每表编号来自既有稳定结果排序，不截短哈希，也不跨会话错联。
        for table in ('events', 'segments', 'sequences', 'calculations'):
            if table not in self.owner.spool.tables:
                continue
            for number, row in enumerate(self._rows(table), 1):
                payload = _json(row)
                identity = tuple(row[name] for name in IDENTITY)
                if table == 'calculations':
                    name, scope = row['calculation_id'], row['scope']
                    definition = (row['unit'], row['operation'])
                    if scope != 'session':
                        self._number('events' if scope == 'event' else 'segments', row, row['parent_id'])
                    if name not in self.metrics[scope]:
                        _reserve_owned_ram(self, 2048 + 64 * (len(name) + len(row['unit'])), '_ram_cost')
                        self.metrics[scope][name] = definition
                    elif self.metrics[scope][name] != definition:
                        raise ResultFormatError('同名计算的单位或算子不一致')
                    self._execute('INSERT INTO metrics VALUES(?,?,?,?,?,?,?)',
                                  (*identity, scope, row['parent_id'] or '', name, payload), len(payload))
                    # session本身也是关联对象；多项指标只建立一次会话结果行。
                    if scope == 'session':
                        self._execute('INSERT OR IGNORE INTO objects VALUES(?,?,?,?,?,?,?)',
                                      ('calculations', *identity, '', number, _json(dict(zip(IDENTITY, identity)))), len(payload))
                else:
                    key = {'events': 'event_id', 'segments': 'segment_id', 'sequences': 'result_id'}[table]
                    self._execute('INSERT INTO objects VALUES(?,?,?,?,?,?,?)',
                                  (table, *identity, row[key], number, payload), len(payload))
        # 一次发布共用事务，避免每条结果触发一次磁盘提交；缓存与页面上限仍逐次生效。
        self.connection.execute('COMMIT')
        self.confirmation = bool({'sequences', 'segments'} & set(self.owner.spool.tables)) or not self.metrics['event'] or any(
            operation != 'integral' for _, operation in self.metrics['event'].values())
        if not self.confirmation:
            # 同一计划可能还有独立事件；不能因别的规则做了积分就隐藏其确认时刻。
            self.confirmation = self.connection.execute(
                "SELECT 1 FROM objects o WHERE o.kind='events' AND NOT EXISTS "
                "(SELECT 1 FROM metrics m WHERE m.d=o.d AND m.e=o.e AND m.s=o.s "
                "AND m.scope='event' AND m.parent=o.id) LIMIT 1").fetchone() is not None

    def _number(self, kind, row, identifier):
        """将完整父ID映射为本次表编号，缺失关系直接报错。

        参数: kind为events/segments，row含完整身份，identifier可为None。
        返回: 编号或空字符串。异常: ResultFormatError为悬空父关联。
        """
        if identifier is None:
            return ''
        if self.connection is None:
            raise ResultFormatError('可读输出缺少父结果')
        found = self.connection.execute('SELECT n FROM objects WHERE kind=? AND d=? AND e=? AND s=? AND id=?',
                                        (kind, *(row[k] for k in IDENTITY), identifier)).fetchone()
        if found is None:
            raise ResultFormatError(f'可读输出缺少{kind}父结果，不能静默丢失关联')
        return found[0]

    def _metric_columns(self, scope):
        """创建已付预算的有限指标列。参数: scope。返回: 列名列表。异常: 无。"""
        columns = []
        for name, (unit, operation) in self.metrics[scope].items():
            # min_time是时间范围内最小值，不是最小时刻；指标单位必须原样保留。
            columns.extend((f'{name}（{unit}）', f'{name}：状态', f'{name}：说明'))
        return columns

    def _metric_values(self, scope, row, parent):
        """按同一完整身份取指标，未产生的指标不伪装为完整或零。

        参数: scope/row/parent定位范围。返回: 有限单行列表。异常: 关联/JSON错误传播。
        """
        values = []
        for name, (unit, operation) in self.metrics[scope].items():
            found = self.connection.execute('SELECT payload FROM metrics WHERE d=? AND e=? AND s=? AND scope=? AND parent=? AND name=?',
                (*(row[k] for k in IDENTITY), scope, parent or '', name)).fetchone()
            if found is None:
                values.extend(('', '无此项结果', ''))
                continue
            metric = json.loads(found[0])
            value = metric['value']
            values.extend((value, STATES.get(metric['status'], metric['status']), explanation(metric)))
        return values

    def _base(self, table, row, number):
        """形成业务列，保留事件/窗口/配对不同含义。

        参数: table、平坦row、本次number。返回: 单行列表。异常: 悬空关联传播。
        """
        if table == 'calculations':
            return self._metric_values('session', row, '')
        if table == 'events':
            values = [number, row['rule_id'], seconds(row['start_ns'])]
            if self.confirmation:
                values.append(seconds(row['confirmed_ns']))
            values.extend((seconds(row['end_ns']), STATES[row['status']], quality_text(row['quality'])))
            return values + self._metric_values('event', row, row['event_id'])
        if table == 'segments':
            return [number, row['window_id'], seconds(row['start_ns']), seconds(row['end_ns']),
                    STATES[row['status']], '、'.join(str(self._number('events', row, p)) for p in row['parent_event_ids']),
                    quality_text(row['quality'])] + self._metric_values('segment', row, row['segment_id'])
        return [number, row['rule_id'], self._number('events', row, row['request_id']),
                self._number('events', row, row['response_id']), seconds(row['decided_ns']), seconds(row['delay_ns']),
                STATES[row['status']], quality_text(row['quality'])]

    def _write(self, table, columns, rows):
        """直接写最终CSV并随写计算可选摘要，不写后回读。

        参数: table/columns/rows为本次有限列与流。返回: 路径。异常: 编码、IO或取消传播。
        """
        path = self.directory / FILES[table]
        digest = hashlib.sha256() if self.owner.metadata.integrity_diagnostics else None
        count, size = 0, 0
        # BOM使Windows表格软件能直接识别中文；仅可读CSV使用它。
        with path.open('xb') as handle:
            header = b'\xef\xbb\xbf'
            handle.write(header)
            size += len(header)
            if digest is not None:
                digest.update(header)
            # StringIO每次只持一条CSV，避免跨结果累计。
            import io
            buffer = io.StringIO(newline='')
            writer = csv.writer(buffer)
            for index, values in enumerate(_with_header(columns, rows)):
                buffer.seek(0)
                buffer.truncate(0)
                writer.writerow(values)
                payload = buffer.getvalue().encode('utf-8')
                if handle.write(payload) != len(payload):
                    raise OSError('可读CSV写入不完整')
                size += len(payload)
                if digest is not None:
                    digest.update(payload)
                if index:
                    count += 1
        self.counts[table] = count
        info = dict(name=path.name, bytes=size)
        if digest is not None:
            info['sha256'] = digest.hexdigest()
        self.infos[path.name] = info
        return path

    def write(self, quality_handle=None, coverage=None):
        """发布全部关联主表；明细由后续专门分支逐条处理。

        参数: quality_handle/coverage为显式质量诊断，默认不生成。返回: 路径tuple。
        异常: 关联/预算/IO错误传播。
        """
        self.quality_handle, self.coverage = quality_handle, coverage
        self.prepare()
        identity = self.owner.spool.identity_summary or (None, None, None)
        self.varying = tuple(index for index, value in enumerate(identity) if value is None)
        paths = []
        columns = {
            'calculations': self._metric_columns('session'),
            'events': ['区间', '规则', '开始时间（s）'] + (['确认时间（s）'] if self.confirmation else [])
                + ['结束时间（s）', '区间状态', '说明'] + self._metric_columns('event'),
            'segments': ['窗口编号', '窗口', '开始时间（s）', '结束时间（s）', '窗口状态', '父事件区间', '说明']
                + self._metric_columns('segment'),
            'sequences': ['配对编号', '规则', '请求区间', '响应区间', '判定时间（s）', '延迟（s）', '配对状态', '说明'],
        }
        for table in ('events', 'segments', 'calculations', 'sequences'):
            if table not in self.owner.spool.tables:
                continue
            if table == 'calculations' and not self.metrics['session']:
                continue
            paths.append(self._write(table, [LABELS[i] for i in self.varying] + columns[table], self._main_rows(table)))
        # 明细无需重排或宽表聚合，直接从原暂存逐行写出，不进入SQLite索引。
        detail_columns = {
            'aggregations': ['聚合项','分组','结果','单位','状态','原因','候选数','参与数','定义排除数','质量排除数',
                             '参与的部分值','匹配','确认超时','观测不足','未决','已完整发现总体','质量说明'],
            'selections': ['计算项', '统计范围', '所属区间', '时间（s）', '值', '单位', '数值状态', '选择状态', '说明'],
            'contributions': ['计算项', '来源', '原记录序号', '求值序号', '贡献值', '说明'],
            'input_trace': ['来源', '原记录序号', '时间（s）', '记录类型', '输入位置', '字段值', '说明'],
        }
        for table, names in detail_columns.items():
            if table in self.owner.spool.tables:
                paths.append(self._write(table, [LABELS[i] for i in self.varying] + names, self._detail_rows(table)))
        return tuple(paths)

    def _detail_rows(self, table):
        """直接输出请求的明细，保留未知、值类型及必要定位。

        参数: table为明细表。返回: 有界CSV行。异常: 缺失父对象或原读取错误。
        """
        for row in self._rows(table):
            if table == 'aggregations':
                values=[row['aggregation_id'],_json(dict(zip(row['group_keys'],row['group_values']))),
                        row['value'],row['unit'],{'complete':'完整','partial':'部分','indeterminate':'不能确定','empty':'确定为空'}[row['status']],
                        {'ok':'正常','partial_population':'总体不完整','no_observation':'无观测','insufficient_data':'观测不足',
                         'empty_population':'无参与值','insufficient_count':'样本数不足','numeric_error':'数值不能确定'}[row['reason']],
                        row['candidate_count'],row['included_count'],row['definition_excluded_count'],row['quality_excluded_count'],
                        row['included_partial_count'],row['matched_count'],row['timeout_count'],row['insufficient_observation_count'],
                        row['pending_count'],'是' if row['discovery_complete'] else '否',quality_text(row['quality'])]
            elif table == 'selections':
                scope = row['scope']
                parent = '' if scope == 'session' else self._number(
                    'events' if scope == 'event' else 'segments', row, row['parent_id'])
                values = [row['calculation_id'], {'session': '会话', 'event': '事件', 'segment': '窗口'}[scope],
                          parent, seconds(row['time_ns']), row['value'], row['unit'],
                          '有效' if row['valid'] else '无效', STATES[row['selection']], explanation(row)]
            elif table == 'contributions':
                values = [row['calculation_id'], row['source'], row['original_sequence'], row['evaluation_index'],
                          row['value'], explanation(row)]
            else:
                kinds = {'decoded_message': '解码报文', 'signal_sample': '信号样本', 'signal_clock': '信号时刻'}
                values = [row['source'], row['original_sequence'], seconds(row['time_ns']), kinds[row['record_type']],
                          row['locator'], row['values_json'], quality_text(row['quality'])]
            yield [row[IDENTITY[i]] for i in self.varying] + values

    def _main_rows(self, table):
        """按索引顺序产生一行，查询不在RAM排序全表。

        参数: table为主表。返回: CSV行生成器。异常: JSON/关联错误。
        """
        if self.connection is None:
            return
        with closing(self.connection.execute('SELECT n,payload FROM objects WHERE kind=? ORDER BY n', (table,))) as cursor:
            for number, payload in cursor:
                row = json.loads(payload)
                yield [row[IDENTITY[i]] for i in self.varying] + self._base(table, row, number)

    def presentation(self):
        """仅返回共同身份和必要使用说明，不增加ID映射副本。

        参数: 无。返回: 清单字典。异常: 无。
        """
        return dict(version=1, time_unit='s', time_coordinates='保留原分析时间坐标，不从零重排，不推断日期或时区',
                    empty_cell='无数值；请结合本指标状态和说明，不等于0',
                    common_identity={IDENTITY[i]: value for i, value in enumerate(self.owner.spool.identity_summary or ())
                                     if value is not None})

    def close(self):
        """关闭并删除本次索引，失败保留真实owner供重试。

        参数: 无。返回: None。异常: IO/释放错误传播，不删除输入或其他文件。
        """
        if self.closed:
            return
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        self.path.unlink(missing_ok=True)
        self.metrics.clear()
        _release_owned_ram(self, self._ram_cost, '_ram_cost')
        self.closed = True


def _with_header(columns, rows):
    """逐条提供表头及内容。参数: columns/rows。返回: 生成器。异常: 原流错误传播。"""
    yield columns
    yield from rows
