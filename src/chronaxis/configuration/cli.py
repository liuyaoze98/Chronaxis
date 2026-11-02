"""配置辅助命令；复用同一模板及配置入口，不执行分析。"""
from .template_catalog import available_templates
from .initialization import initialize_configuration


def run_configuration_cli(arguments):
    """执行已解析的配置命令。参数: argparse结果。返回: 退出码。异常: 配置/文件/取消上交CLI。

    初始化显示实际入口与合成预期；可运行不代表适合真实设备。
    """
    if arguments.config_command=='origins':
        from .origins import configuration_origins,render_origins
        import json
        report=configuration_origins(arguments.input,fields=arguments.fields)
        print(json.dumps(report,ensure_ascii=False,indent=2) if arguments.format=='json' else render_origins(report),
              end='\n' if arguments.format=='json' else '')
        return 0
    if arguments.config_command=='convert':
        from .file_tools import convert_configuration
        path=convert_configuration(arguments.input,arguments.output)
        print('已转换：'+str(path)+'；配置类型和值保持，注释不保留。')
        return 0
    if arguments.config_command=='resolve':
        from .resolution import resolve_configuration
        result=resolve_configuration(arguments.input,output=arguments.output,format=arguments.format,defaults=arguments.defaults)
        if arguments.output is None:print(result,end='')
        else:print('已导出有效配置：'+str(result)+'；路径固定为原输入的绝对位置。')
        return 0
    if arguments.list:
        if arguments.scene is not None or arguments.output is not None:
            raise ValueError('--list不能同时指定场景或输出目录')
        for template in available_templates():print(template.name+' — '+template.title)
        return 0
    if arguments.scene is None or arguments.output is None:
        raise ValueError('初始化需要场景名和--output新目录；用--list查看场景')
    path=initialize_configuration(arguments.scene,arguments.output,style=arguments.style)
    template=next(t for t in available_templates() if t.name==arguments.scene)
    print('已生成合成场景：'+str(path))
    print('预期：'+template.expected)
    print('真实使用前请核实单位、方向、有效期和阈值。')
    return 0
