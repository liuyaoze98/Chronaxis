"""将python -m chronaxis委托给同一个CLI入口。

输入为进程参数，输出及退出码由cli.main定义。作为模块导入时不运行命令；
实际执行只加载CLI，再由用户命令决定检查配置、运行分析或处理结果。
本文件不另写计算逻辑、加载CAN或注册额外后台动作。
"""

from .cli import main

if __name__ == '__main__':
    # 两种入口共用解析与错误处理，SystemExit保主函数的真实退出码。
    raise SystemExit(main())
