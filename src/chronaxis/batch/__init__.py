"""公开独立批量任务模型和调度器，不自动创建进程或读取输入。

每个BatchJob调用同一公共AnalysisRunner，输出单独发布，BatchReport只汇总状态和身份。
调用者可设置process_count工作进程数、fail_fast和取消Event；在途任务完成关闭后才返回。
"""

from .models import BatchJob, BatchJobResult, BatchReport, BatchPlan
from .runner import BatchRunner
from .config import load_batch_plan
from .api import run_batch
from .publication import write_batch_report

__all__ = ['BatchJob', 'BatchJobResult', 'BatchReport', 'BatchRunner', 'BatchPlan',
           'load_batch_plan', 'run_batch', 'write_batch_report']
