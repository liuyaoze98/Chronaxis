"""保存清单中的预设版本与最终角色，不读取来源或重新执行工程契约。

输入是计划构建器已检查、运行层又与实际绑定核对的有限角色记录，输出为冻结
快照。记录只有别名和契约追溯，不含样本或原配置。contract_status仅表示给定
声明元数据通过了检查，不能证明方向、位置或物理语义已经由系统测量核实。
本模块只依赖标准库与核心字段校验，无I/O、预算或状态副作用。
"""

# 完整信号定义由RunMetadata另存；角色快照只引用同一清单的实际简单别名。
from dataclasses import dataclass
from ..core.validation import require_identifier, require_text


@dataclass(frozen=True)
class PresetRoleMetadata:
    """保留角色选择和声明契约版本，字段冻结且不代表物理事实已验。"""

    role: str  # 原预设角色。
    alias: str  # 最终实际信号别名。
    resolution: str  # explicit或semantic_unique。
    contract_version: str  # 实际检查的角色契约版本。
    contract_status: str = 'checked_against_declared_metadata'  # 校验的是给定声明。

    def __post_init__(self):
        """校验有限字段，不执行角色契约。参数: 无。返回: None。异常: 类型或非法状态。"""
        require_identifier(self.role, 'preset_role.role')
        require_identifier(self.alias, 'preset_role.alias')
        require_text(self.contract_version, 'preset_role.contract_version')
        # 两种选择方式都先由原构建器完成，不接受未知方式或升级后的物理验证状态。
        if self.resolution not in ('explicit', 'semantic_unique'):
            raise ValueError('预设角色查找方式需explicit或semantic_unique')
        if self.contract_status != 'checked_against_declared_metadata':
            raise ValueError('预设角色状态只能说明已检查声明元数据')


@dataclass(frozen=True)
class PresetBindingMetadata:
    """按原计划顺序保存一个预设的版本和全部角色，角色不可重复。"""

    preset_id: str  # 原预设ID。
    preset_type: str  # 原预设种类，不从名称推断领域事实。
    version: str  # 原预设版本，与角色契约版本独立。
    roles: tuple[PresetRoleMetadata, ...]  # 有限冻结记录，不含输入行。

    def __post_init__(self):
        """核快照及角色唯一性。参数: 无。返回: None。异常: 类型、空身份或重复角色。"""
        require_identifier(self.preset_id, 'preset_binding.preset_id')
        require_text(self.preset_type, 'preset_binding.preset_type')
        require_text(self.version, 'preset_binding.version')
        if type(self.roles) is not tuple or any(type(role) is not PresetRoleMetadata for role in self.roles):
            raise TypeError('预设清单角色需冻结PresetRoleMetadata tuple')
        # 模型只检查内部结构；运行层另证别名和定义属于本次实际输入。
        if len({role.role for role in self.roles}) != len(self.roles):
            raise ValueError('预设清单不能重复同一角色')
