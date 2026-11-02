"""只覆盖公共定义中的明确配置项，不允许隐藏改名、添加对象或递归合并自由数据。

覆盖值按主文件定位，随后仍由普通计划校验器检查；来源表同时指回真正的覆盖位置。
"""
from copy import deepcopy
from .models import ConfigurationOrigin

ALLOWED={
    'sources':{'path','paths','dbc_by_channel','time','reader'},
    'signals':{'dtype','unit','valid_for','period','conversion','choices','valid_range','invalid_values','sample_policy','same_time_policy'},
    'derived':{'expr','unit'},
}


def apply_overrides(target, document, prefix, locations, origins):
    """修改本次独立副本；参数含原文位置。返回None；非法对象/字段经_imports._reject定位。"""
    from .imports import _reject, _source_paths
    from pathlib import Path
    raw=target.pop('overrides',{})
    if type(raw) is not dict or set(raw)-set(ALLOWED):
        _reject(document,(*prefix,'overrides'),'overrides仅允许sources/signals/derived对象')
    for section,items in raw.items():
        where=(*prefix,'overrides',section)
        if type(items) is not dict:_reject(document,where,'覆盖项须按已有名称索引')
        catalog={}
        if section=='derived':
            catalog={name:(value,(*prefix,section,name)) for name,value in target.get(section,{}).items()}
        else:
            for index,value in enumerate(target.get(section,[])):
                if section=='signals' and 'signals' in value:
                    for ci,child in enumerate(value['signals']):catalog[child['name']]=(child,(*prefix,section,index,'signals',ci))
                else:catalog[value['name']]=(value,(*prefix,section,index))
        for name,changes in items.items():
            path=(*where,name)
            if name not in catalog:_reject(document,path,'覆盖目标不存在，不允许新增定义')
            if type(changes) is not dict or not changes or set(changes)-ALLOWED[section]:
                _reject(document,path,'覆盖字段不在允许列表；不能改名、改绑定或修改自由metadata')
            value,target_path=catalog[name]
            # path/paths是同一输入声明的两种形状，只保留用户本次选定的一种。
            if section=='sources':
                if 'path' in changes and 'paths' not in changes:value.pop('paths',None)
                if 'paths' in changes and 'path' not in changes:value.pop('path',None)
            # 被整体替换的字段不再保留旧叶子来源，例如旧time.clock已被省略。
            replaced=set(changes)
            if section=='sources' and replaced & {'path','paths'}:replaced.update(('path','paths'))
            for effective in tuple(origins):
                if effective[:len(target_path)]==target_path and len(effective)>len(target_path) and effective[len(target_path)] in replaced:
                    origins.pop(effective,None);locations.pop(effective,None)
            value.update(deepcopy(changes))
            if section=='sources':_source_paths(value,Path(document.source).parent,path,document)
            for original,location in document.locations.items():
                if original[:len(path)]==path and len(original)>len(path):
                    effective=(*target_path,*original[len(path):])
                    locations[effective]=location
                    origins[effective]=ConfigurationOrigin(document.source,original,location)
