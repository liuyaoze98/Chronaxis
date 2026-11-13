# 配置字段完整参考

> 基线8904c2f744951857659abd40aaa3535d57faf53c；device_label: home。

先读[配置教程](../configuration.md)。JSON路径含`$defs`的条目是可复用结构；`$ref`指向这些结构。schema描述形状，运行能力由计划解析和AnalysisRunner校验决定，不能据枚举值推断已接线。

## `$`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$comment": "分析配置格式4；本地相对引用。字段结构由本规范检查，展开后的跨字段约束由计划模型检查。",
  "title": "Chronaxis 当前分析配置",
  "description": "当前分析配置版本4，兼容单位自动换算。默认采用真实记录间隔，按请求生成结果；引用、单位、驱动与时间范围由AnalysisPlan检查。",
  "type": "object",
  "required": [
    "config_version",
    "dataset"
  ],
  "additionalProperties": false,
  "dependentRequired": {
    "overrides": [
      "imports"
    ]
  }
}
```

## `$.allOf[0].properties.signals`

```json
{
  "description": "约束当前版本可以使用的信号声明字段。"
}
```

## `$.allOf[0].properties.signals.items`

```json
{
  "dependentSchemas": {
    "code_dtype": {
      "properties": {
        "dtype": {
          "const": "enum",
          "description": "信号值的类型，决定该信号可用的附加字段。"
        }
      }
    }
  }
}
```

## `$.allOf[0].properties.signals.items.properties.signals`

```json
{
  "description": "约束当前版本可以使用的信号声明字段。"
}
```

## `$.allOf[0].properties.signals.items.properties.signals.items`

```json
{
  "dependentSchemas": {
    "code_dtype": {
      "properties": {
        "dtype": {
          "const": "enum",
          "description": "信号值的类型，决定该信号可用的附加字段。"
        }
      }
    }
  }
}
```

## `$.allOf[1]`

```json
{
  "$comment": "省略domain时由同次读取确定实际观测范围，普通分析与按需导出均可使用。"
}
```

## `$.allOf[2]`

```json
{
  "if": {
    "properties": {
      "sources": {
        "items": {
          "properties": {
            "source_type": {
              "enum": [
                "memory",
                "signal_csv"
              ],
              "description": "数据来源类型，决定使用哪个读取器及其必需字段。可选值：\"memory\"：配置内有序内存记录；\"signal_csv\"：已解码信号CSV。"
            }
          },
          "required": [
            "source_type"
          ]
        },
        "description": "按声明顺序列出数据来源。连续文件放在同一来源的paths中；加载时可按声明枚举文件名，并按缺省信号信息读取DBC；不读取业务记录。"
      }
    },
    "required": [
      "sources"
    ],
    "not": {
      "required": [
        "imports"
      ]
    }
  },
  "then": {
    "properties": {
      "signals": {
        "items": {
          "properties": {
            "field": {
              "type": "string",
              "minLength": 1,
              "pattern": "\\S",
              "description": "来源中的真实字段。信号表/内存使用原字段名，CAN使用完整通道和报文信号定位对象。"
            }
          },
          "not": {
            "required": [
              "signals"
            ]
          }
        },
        "description": "把来源的原始字段绑定为分析使用的简单信号名，明确类型、单位和有效期。"
      }
    }
  }
}
```

## `$.allOf[3]`

```json
{
  "if": {
    "properties": {
      "sources": {
        "items": {
          "properties": {
            "source_type": {
              "enum": [
                "can_blf",
                "can_asc",
                "raw_can_csv"
              ],
              "description": "数据来源类型，决定使用哪个读取器及其必需字段。可选值：\"can_blf\"：原始CAN二进制BLF；\"can_asc\"：原始CAN文本ASC；\"raw_can_csv\"：显式布局的原始CAN帧CSV。"
            }
          },
          "required": [
            "source_type"
          ]
        },
        "description": "按声明顺序列出数据来源。连续文件放在同一来源的paths中；加载时可按声明枚举文件名，并按缺省信号信息读取DBC；不读取业务记录。"
      }
    },
    "required": [
      "sources"
    ],
    "not": {
      "required": [
        "imports"
      ]
    }
  },
  "then": {
    "properties": {
      "signals": {
        "items": {
          "properties": {
            "field": {
              "type": "object",
              "properties": {
                "channel": {
                  "type": "integer",
                  "minimum": 1,
                  "description": "用户配置CAN通道从1开始，1对应内部0；省略时继承来源唯一通道。"
                },
                "signal": {
                  "type": "string",
                  "minLength": 1,
                  "description": "DBC中该信号的原始名称，与frame_id一起定位同一报文内的信号；这里不是分析别名。"
                },
                "frame_id": {
                  "oneOf": [
                    {
                      "type": "integer",
                      "minimum": 0,
                      "maximum": 536870911
                    },
                    {
                      "type": "string",
                      "pattern": "^(?:[0-9]+|0[xX][0-9a-fA-F]+|0[bB][01]+)(?![\\s\\S])",
                      "minLength": 1
                    }
                  ],
                  "description": "CAN报文ID；整数或字符串均可。0x前缀为十六进制，0b为二进制，无前缀为十进制；解析后须在0至536870911内，显式标准帧最多2047。"
                },
                "is_extended": {
                  "type": "boolean",
                  "description": "标准／扩展帧可选约束。省略时根据DBC和实际报文识别；只有歧义时要求补充。显式null无效。"
                },
                "is_fd": {
                  "type": "boolean",
                  "description": "CAN／CAN FD可选约束。省略时根据DBC和实际报文识别；只有歧义时要求补充。显式null无效。"
                }
              },
              "required": [
                "signal",
                "frame_id"
              ],
              "additionalProperties": false,
              "description": "来源中的真实字段。信号表/内存使用原字段名，CAN使用完整通道和报文信号定位对象。",
              "allOf": [
                {
                  "if": {
                    "properties": {
                      "is_extended": {
                        "const": false,
                        "description": "显式选择标准帧时，整数ID不得超过11位范围。"
                      }
                    },
                    "required": [
                      "is_extended"
                    ]
                  },
                  "then": {
                    "properties": {
                      "frame_id": {
                        "maximum": 2047,
                        "description": "标准帧的整数报文ID上限为2047；字符串转换后的范围由计划加载器核实。"
                      }
                    }
                  }
                }
              ]
            }
          }
        },
        "description": "把来源的原始字段绑定为分析使用的简单信号名，明确类型、单位和有效期。"
      }
    }
  }
}
```

## `$.anyOf[0]`

```json
{
  "required": [
    "imports"
  ]
}
```

## `$.anyOf[1]`

```json
{
  "required": [
    "sources",
    "signals"
  ]
}
```

## `$.properties.config_version`

```json
{
  "type": "integer",
  "description": "分析配置结构编号，只接受整数4；旧版本、缺失和错误类型均拒绝，不自动转换。",
  "const": 4
}
```

## `$.properties.transforms`

```json
{
  "type": "array",
  "maxItems": 64,
  "description": "版本4在原记录或指定输出时刻计算滚动数值和变化率。"
}
```

## `$.properties.transforms.items`

```json
{
  "type": "object",
  "required": [
    "name",
    "operation",
    "expr"
  ],
  "additionalProperties": false
}
```

## `$.properties.transforms.items.allOf[0]`

```json
{
  "if": {
    "required": [
      "operation"
    ],
    "properties": {
      "operation": {
        "$ref": "#/properties/transforms/items/properties/operation",
        "description": "选择这项计算执行的具名操作。"
      }
    }
  },
  "then": {
    "if": {
      "properties": {
        "operation": {
          "const": "adjacent_rate",
          "description": "选择这项计算执行的具名操作。"
        }
      }
    },
    "then": {
      "required": [
        "max_gap"
      ],
      "properties": {
        "window": {
          "not": {},
          "description": "在当前版本或操作下不能填写字段 window。"
        },
        "step": {
          "not": {},
          "description": "在当前版本或操作下不能填写字段 step。"
        },
        "origin": {
          "not": {},
          "description": "在当前版本或操作下不能填写字段 origin。"
        },
        "partial_policy": {
          "not": {},
          "description": "在当前版本或操作下不能填写字段 partial_policy。"
        },
        "minimum_coverage": {
          "not": {},
          "description": "在当前版本或操作下不能填写字段 minimum_coverage。"
        }
      }
    },
    "else": {
      "required": [
        "window",
        "step"
      ],
      "properties": {
        "max_gap": {
          "not": {},
          "description": "在当前版本或操作下不能填写字段 max_gap。"
        }
      }
    }
  }
}
```

## `$.properties.transforms.items.properties.name`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "用户给这一项起的名称，后续通过此名称引用它。"
}
```

## `$.properties.transforms.items.properties.operation`

```json
{
  "enum": [
    "rolling_time_mean",
    "rolling_minimum",
    "rolling_maximum",
    "rolling_integral",
    "adjacent_rate",
    "window_rate",
    "sample_fit_slope"
  ],
  "description": "选择这项计算执行的具名操作。"
}
```

## `$.properties.transforms.items.properties.expr`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "从已绑定的信号或派生量计算此项的输入。"
}
```

## `$.properties.transforms.items.properties.unit`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "希望结果采用的单位，必须与计算量兼容。"
}
```

## `$.properties.transforms.items.properties.window`

```json
{
  "type": "string",
  "pattern": "^\\s*[+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "选择窗口范围；变换中的时长必须为正。"
}
```

## `$.properties.transforms.items.properties.step`

```json
{
  "type": "string",
  "pattern": "^\\s*[+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "两次定时输出之间的实际时间距离，必须为正。"
}
```

## `$.properties.transforms.items.properties.origin`

```json
{
  "type": "string",
  "description": "用来对齐输出网格的实际时刻，使用本来源的时间坐标。"
}
```

## `$.properties.transforms.items.properties.max_gap`

```json
{
  "type": "string",
  "pattern": "^\\s*[+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "相邻两次实际更新允许相隔的最长时间。"
}
```

## `$.properties.transforms.items.properties.partial_policy`

```json
{
  "enum": [
    "strict",
    "report"
  ],
  "description": "部分数据可用时，决定保留数值还是返回空值。"
}
```

## `$.properties.transforms.items.properties.minimum_coverage`

```json
{
  "type": "number",
  "minimum": 0,
  "maximum": 1,
  "description": "有效数据占所请求窗口的最低比例。"
}
```

## `$.properties.transforms.items.properties.interval`

```json
{
  "$ref": "#/properties/calculations/items/properties/interval",
  "description": "选择以实测、固定或原始报文DBC周期计算间隔。"
}
```

## `$.properties.aggregations`

```json
{
  "type": "array",
  "description": "按需汇总单次运行中的计算、配对、事件或窗口结果。"
}
```

## `$.properties.aggregations.items`

```json
{
  "type": "object",
  "required": [
    "name",
    "source",
    "operation"
  ],
  "additionalProperties": false
}
```

## `$.properties.aggregations.items.allOf[0]`

```json
{
  "if": {
    "required": [
      "operation"
    ],
    "properties": {
      "operation": {
        "$ref": "#/properties/aggregations/items/properties/operation",
        "description": "对引用的结果行执行的聚合。成功响应的延迟均值和P95只使用已成功配对的延迟。"
      }
    }
  },
  "then": {
    "allOf": [
      {
        "if": {
          "properties": {
            "operation": {
              "const": "quantile",
              "description": "选择这项计算执行的具名操作。"
            }
          }
        },
        "then": {
          "required": [
            "q"
          ]
        },
        "else": {
          "properties": {
            "q": {
              "not": {},
              "description": "在当前版本或操作下不能填写字段 q。"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "operation": {
              "const": "variance",
              "description": "选择这项计算执行的具名操作。"
            }
          }
        },
        "else": {
          "properties": {
            "ddof": {
              "not": {},
              "description": "在当前版本或操作下不能填写字段 ddof。"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "operation": {
              "const": "count",
              "description": "选择这项计算执行的具名操作。"
            }
          }
        },
        "then": {
          "properties": {
            "field": {
              "not": {},
              "description": "在当前版本或操作下不能填写字段 field。"
            },
            "unit": {
              "const": "1",
              "description": "希望结果采用的单位，必须与计算量兼容。"
            }
          }
        }
      },
      {
        "if": {
          "required": [
            "source"
          ],
          "properties": {
            "source": {
              "$ref": "#/properties/aggregations/items/properties/source",
              "description": "选择本次运行要汇总的结果。只引用一个计算、配对、规则或窗口。"
            }
          }
        },
        "then": {
          "if": {
            "properties": {
              "source": {
                "required": [
                  "sequence"
                ],
                "description": "指定聚合所用的一种结果及其名称。"
              }
            }
          },
          "then": {
            "properties": {
              "group_by": {
                "items": {
                  "enum": [
                    "dataset_id",
                    "entity_id",
                    "session_id",
                    "sequence_id"
                  ],
                  "description": "当前结果来源可用的分组字段；每个字段最多选一次。"
                },
                "description": "用选定来源已有的标识对结果行分组。"
              },
              "field": {
                "const": "delay_ns",
                "description": "指定这项统计从结果行读取的数值列。"
              }
            }
          }
        }
      },
      {
        "if": {
          "required": [
            "source"
          ],
          "properties": {
            "source": {
              "$ref": "#/properties/aggregations/items/properties/source",
              "description": "选择本次运行要汇总的结果。只引用一个计算、配对、规则或窗口。"
            }
          }
        },
        "then": {
          "if": {
            "properties": {
              "source": {
                "required": [
                  "calculation"
                ],
                "description": "指定聚合所用的一种结果及其名称。"
              }
            }
          },
          "then": {
            "properties": {
              "group_by": {
                "items": {
                  "enum": [
                    "dataset_id",
                    "entity_id",
                    "session_id",
                    "calculation_id",
                    "parent_id"
                  ],
                  "description": "当前结果来源可用的分组字段；每个字段最多选一次。"
                },
                "description": "用选定来源已有的标识对结果行分组。"
              },
              "field": {
                "const": "value",
                "description": "指定这项统计从结果行读取的数值列。"
              }
            }
          }
        }
      },
      {
        "if": {
          "required": [
            "source"
          ],
          "properties": {
            "source": {
              "$ref": "#/properties/aggregations/items/properties/source",
              "description": "选择本次运行要汇总的结果。只引用一个计算、配对、规则或窗口。"
            }
          }
        },
        "then": {
          "if": {
            "properties": {
              "source": {
                "required": [
                  "rule"
                ],
                "description": "指定聚合所用的一种结果及其名称。"
              }
            }
          },
          "then": {
            "properties": {
              "group_by": {
                "items": {
                  "enum": [
                    "dataset_id",
                    "entity_id",
                    "session_id",
                    "rule_id"
                  ],
                  "description": "当前结果来源可用的分组字段；每个字段最多选一次。"
                },
                "description": "用选定来源已有的标识对结果行分组。"
              },
              "operation": {
                "const": "count",
                "description": "选择这项计算执行的具名操作。"
              },
              "field": {
                "not": {},
                "description": "在当前版本或操作下不能填写字段 field。"
              }
            }
          }
        }
      },
      {
        "if": {
          "required": [
            "source"
          ],
          "properties": {
            "source": {
              "$ref": "#/properties/aggregations/items/properties/source",
              "description": "选择本次运行要汇总的结果。只引用一个计算、配对、规则或窗口。"
            }
          }
        },
        "then": {
          "if": {
            "properties": {
              "source": {
                "required": [
                  "window"
                ],
                "description": "指定聚合所用的一种结果及其名称。"
              }
            }
          },
          "then": {
            "properties": {
              "group_by": {
                "items": {
                  "enum": [
                    "dataset_id",
                    "entity_id",
                    "session_id",
                    "window_id"
                  ],
                  "description": "当前结果来源可用的分组字段；每个字段最多选一次。"
                },
                "description": "用选定来源已有的标识对结果行分组。"
              },
              "operation": {
                "const": "count",
                "description": "选择这项计算执行的具名操作。"
              },
              "field": {
                "not": {},
                "description": "在当前版本或操作下不能填写字段 field。"
              }
            }
          }
        }
      }
    ]
  }
}
```

## `$.properties.aggregations.items.properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "用户给这一项起的名称，后续通过此名称引用它。"
}
```

## `$.properties.aggregations.items.properties.source`

```json
{
  "type": "object",
  "description": "选择本次运行要汇总的结果。只引用一个计算、配对、规则或窗口。",
  "minProperties": 1,
  "maxProperties": 1,
  "additionalProperties": false
}
```

## `$.properties.aggregations.items.properties.source.properties.calculation`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "引用要汇总的标量计算项的名称。"
}
```

## `$.properties.aggregations.items.properties.source.properties.sequence`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "引用产生请求和响应结果的配对规则名称。"
}
```

## `$.properties.aggregations.items.properties.source.properties.rule`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "引用产生待计数事件的已声明规则。"
}
```

## `$.properties.aggregations.items.properties.source.properties.window`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "description": "引用生成待统计片段的窗口名称。"
}
```

## `$.properties.aggregations.items.properties.operation`

```json
{
  "enum": [
    "count",
    "sum",
    "mean",
    "variance",
    "quantile",
    "median"
  ],
  "description": "对引用的结果行执行的聚合。成功响应的延迟均值和P95只使用已成功配对的延迟。"
}
```

## `$.properties.aggregations.items.properties.field`

```json
{
  "enum": [
    "value",
    "delay_ns"
  ],
  "description": "可选数值字段；计算结果默认value，配对默认delay_ns。计数不需要数值字段。"
}
```

## `$.properties.aggregations.items.properties.group_by`

```json
{
  "type": "array",
  "uniqueItems": true,
  "description": "按这些稳定字段分组。省略时将本次引用结果合为一组。"
}
```

## `$.properties.aggregations.items.properties.group_by.items`

```json
{
  "enum": [
    "dataset_id",
    "entity_id",
    "session_id",
    "calculation_id",
    "parent_id",
    "sequence_id",
    "rule_id",
    "window_id"
  ],
  "description": "当前结果来源可用的分组字段；每个字段最多选一次。"
}
```

## `$.properties.aggregations.items.properties.unit`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "汇总结果的显示单位。计数为1；配对延迟可用ms或s。"
}
```

## `$.properties.aggregations.items.properties.include_partial`

```json
{
  "type": "boolean",
  "description": "是否允许已有的部分数值参与。即使允许，汇总仍保留部分状态。"
}
```

## `$.properties.aggregations.items.properties.partial_policy`

```json
{
  "enum": [
    "report",
    "strict"
  ],
  "description": "总体不完整时，report可给出已知部分，strict不给出数值。"
}
```

## `$.properties.aggregations.items.properties.q`

```json
{
  "type": "number",
  "minimum": 0,
  "maximum": 1,
  "description": "分位数位置，quantile必填。median固定取0.5，不填写q。"
}
```

## `$.properties.aggregations.items.properties.ddof`

```json
{
  "type": "integer",
  "enum": [
    0,
    1
  ],
  "description": "方差的自由度修正，省略为0。"
}
```

## `$.properties.lookups`

```json
{
  "type": "array",
  "maxItems": 64,
  "description": "版本4的一维标定表，供lookup函数按名称引用。输入轴在其声明单位中严格递增，步骤模式保留表值的定宽类型。"
}
```

## `$.properties.lookups.items`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "name",
    "points",
    "input_unit",
    "unit"
  ]
}
```

## `$.properties.lookups.items.properties.name`

```json
{
  "$ref": "#/properties/dataset/properties/name",
  "description": "表达式引用的唯一表名。"
}
```

## `$.properties.lookups.items.properties.input_unit`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256,
  "description": "标定轴单位，兼容的查询输入按此单位换算。"
}
```

## `$.properties.lookups.items.properties.unit`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256,
  "description": "希望结果采用的单位，必须与计算量兼容。"
}
```

## `$.properties.lookups.items.properties.points`

```json
{
  "type": "array",
  "minItems": 2,
  "maxItems": 4096,
  "description": "按输入从小到大排列的[输入,输出]数值对。有限轴、定宽整数和精度由加载器核验。"
}
```

## `$.properties.lookups.items.properties.points.items`

```json
{
  "type": "array",
  "minItems": 2,
  "maxItems": 2
}
```

## `$.properties.lookups.items.properties.points.items.items`

```json
{
  "type": "number"
}
```

## `$.properties.dataset`

```json
{
  "type": "object",
  "required": [
    "name"
  ],
  "additionalProperties": false,
  "description": "本次分析对象、会话与请求时间范围。请求范围不等于实际采集覆盖。"
}
```

## `$.properties.dataset.properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.dataset.properties.entity`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "被分析对象的标识，例如设备或实验编号；通用核心不预设车辆含义。 省略时使用dataset.name。"
}
```

## `$.properties.dataset.properties.session`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "本次共同分析会话的标识。同会话联合信号必须有明确可比较的时间基准。 省略时使用dataset.name，运行状态按任务隔离。"
}
```

## `$.properties.dataset.properties.domain`

```json
{
  "type": "object",
  "required": [
    "start",
    "end"
  ],
  "additionalProperties": false,
  "description": "请求分析的半开时间范围[start,end)，包含起点、不包含终点。普通分析与逐消息累计均可省略，由实际观测确定范围；显式填写时必须同时给出start和end，null或空对象不等于省略。"
}
```

## `$.properties.dataset.properties.domain.properties.start`

```json
{
  "type": "string",
  "description": "分析范围的起点，使用带单位相对时间或明确时区的绝对时刻。"
}
```

## `$.properties.dataset.properties.domain.properties.start.anyOf[0]`

```json
{
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$"
}
```

## `$.properties.dataset.properties.domain.properties.start.anyOf[1]`

```json
{
  "pattern": "^\\s*\\d{4}-\\d{2}-\\d{2}[T ]\\d{2}:\\d{2}:\\d{2}"
}
```

## `$.properties.dataset.properties.domain.properties.end`

```json
{
  "type": "string",
  "description": "分析范围不包含的终点，必须与起点使用相同时间坐标且不早于起点。"
}
```

## `$.properties.dataset.properties.domain.properties.end.anyOf[0]`

```json
{
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$"
}
```

## `$.properties.dataset.properties.domain.properties.end.anyOf[1]`

```json
{
  "pattern": "^\\s*\\d{4}-\\d{2}-\\d{2}[T ]\\d{2}:\\d{2}:\\d{2}"
}
```

## `$.properties.dataset.properties.metadata`

```json
{
  "type": "object",
  "additionalProperties": true,
  "description": "附加说明对象；允许自定义JSON原生值，但不参与隐藏转换、模板执行或业务参数推断。"
}
```

## `$.properties.sources`

```json
{
  "type": "array",
  "minItems": 1,
  "description": "按声明顺序列出数据来源。连续文件放在同一来源的paths中；加载时可按声明枚举文件名，并按缺省信号信息读取DBC；不读取业务记录。"
}
```

## `$.properties.sources.items.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "source_type",
    "rows"
  ],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[0].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "来源在本计划内的名称；省略时按声明位置生成source_1、source_2等。后续source引用使用此名称，不用于猜测原字段或同步。"
}
```

## `$.properties.sources.items.oneOf[0].properties.time`

```json
{
  "description": "来源时间的类型、单位、时钟和偏移设置。time_type省略为relative，clock省略生成来源独立起点；只有有同步依据的多来源才填写共同clock。"
}
```

## `$.properties.sources.items.oneOf[0].properties.time.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[0].properties.time.oneOf[0].properties.unit`

```json
{
  "enum": [
    "s",
    "ms",
    "us",
    "ns"
  ],
  "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。可选值：\"s\"：秒；\"ms\"：毫秒；\"us\"：微秒；\"ns\"：纳秒。"
}
```

## `$.properties.sources.items.oneOf[0].properties.time.oneOf[0].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "应用到来源时间的固定偏移，可正可负，必须带s/ms/us/ns单位；不是时区或日期。",
  "default": "0s"
}
```

## `$.properties.sources.items.oneOf[0].properties.time.oneOf[0].properties.time_type`

```json
{
  "const": "relative",
  "description": "时间坐标类型：相对公共起点，或带时区依据的绝对时间。 固定值：\"relative\"（相对明确公共起点的时间）。"
}
```

## `$.properties.sources.items.oneOf[0].properties.time.oneOf[0].properties.clock`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "相对时间起点的共享名称；仅对确实共用起点的数据填写同一个值，省略不自动同步。"
}
```

## `$.properties.sources.items.oneOf[0].properties.time.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "time_type"
  ],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[0].properties.time.oneOf[1].properties.unit`

```json
{
  "enum": [
    "s",
    "ms",
    "us",
    "ns",
    "ISO8601"
  ],
  "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。可选值：\"s\"：秒；\"ms\"：毫秒；\"us\"：微秒；\"ns\"：纳秒；\"ISO8601\"：包含日期和时区依据的时间文本。"
}
```

## `$.properties.sources.items.oneOf[0].properties.time.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "应用到来源时间的固定偏移，可正可负，必须带s/ms/us/ns单位；不是时区或日期。",
  "default": "0s"
}
```

## `$.properties.sources.items.oneOf[0].properties.time.oneOf[1].properties.timezone`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "绝对时间缺少自身时区时采用的明确时区，例如UTC或IANA名称；不读取机器默认时区作为配置。"
}
```

## `$.properties.sources.items.oneOf[0].properties.time.oneOf[1].properties.time_type`

```json
{
  "const": "absolute",
  "description": "时间坐标类型：相对公共起点，或带时区依据的绝对时间。 固定值：\"absolute\"（有时区依据的绝对时间）。"
}
```

## `$.properties.sources.items.oneOf[0].properties.metadata`

```json
{
  "type": "object",
  "additionalProperties": true,
  "description": "附加说明对象；允许自定义JSON原生值，但不参与隐藏转换、模板执行或业务参数推断。"
}
```

## `$.properties.sources.items.oneOf[0].properties.rows`

```json
{
  "type": "array",
  "description": "内存来源的有序记录数组，每条含time和原字段values；不会自动排序掩盖乱序。"
}
```

## `$.properties.sources.items.oneOf[0].properties.rows.items`

```json
{
  "type": "object",
  "required": [
    "time",
    "values"
  ],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[0].properties.rows.items.properties.time`

```json
{
  "type": "string",
  "description": "来源时间的类型、单位、时钟和偏移设置。time_type省略为relative，clock省略生成来源独立起点；只有有同步依据的多来源才填写共同clock。"
}
```

## `$.properties.sources.items.oneOf[0].properties.rows.items.properties.time.anyOf[0]`

```json
{
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$"
}
```

## `$.properties.sources.items.oneOf[0].properties.rows.items.properties.time.anyOf[1]`

```json
{
  "pattern": "^\\s*\\d{4}-\\d{2}-\\d{2}[T ]\\d{2}:\\d{2}:\\d{2}"
}
```

## `$.properties.sources.items.oneOf[0].properties.rows.items.properties.values`

```json
{
  "type": "object",
  "additionalProperties": {
    "type": [
      "number",
      "string",
      "boolean",
      "null"
    ]
  },
  "description": "本条内存记录的原字段到原生值的映射。原字段可含点号，表达式通过signals别名引用。"
}
```

## `$.properties.sources.items.oneOf[0].properties.source_type`

```json
{
  "const": "memory",
  "description": "数据来源类型，决定使用哪个读取器及其必需字段。 固定值：\"memory\"（配置内有序内存记录）。"
}
```

## `$.properties.sources.items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "source_type",
    "time",
    "time_column"
  ],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[1].oneOf[0]`

```json
{
  "required": [
    "path"
  ],
  "not": {
    "required": [
      "paths"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[1].oneOf[1]`

```json
{
  "required": [
    "paths"
  ],
  "not": {
    "required": [
      "path"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[1].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "来源在本计划内的名称；省略时按声明位置生成source_1、source_2等。后续source引用使用此名称，不用于猜测原字段或同步。"
}
```

## `$.properties.sources.items.oneOf[1].properties.time`

```json
{
  "description": "来源时间的类型、单位、时钟和偏移设置。time_type省略为relative，clock省略生成来源独立起点；只有有同步依据的多来源才填写共同clock。"
}
```

## `$.properties.sources.items.oneOf[1].properties.time.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "unit"
  ],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[1].properties.time.oneOf[0].properties.unit`

```json
{
  "enum": [
    "s",
    "ms",
    "us",
    "ns"
  ],
  "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。可选值：\"s\"：秒；\"ms\"：毫秒；\"us\"：微秒；\"ns\"：纳秒。"
}
```

## `$.properties.sources.items.oneOf[1].properties.time.oneOf[0].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "应用到来源时间的固定偏移，可正可负，必须带s/ms/us/ns单位；不是时区或日期。",
  "default": "0s"
}
```

## `$.properties.sources.items.oneOf[1].properties.time.oneOf[0].properties.time_type`

```json
{
  "const": "relative",
  "description": "时间坐标类型：相对公共起点，或带时区依据的绝对时间。 固定值：\"relative\"（相对明确公共起点的时间）。"
}
```

## `$.properties.sources.items.oneOf[1].properties.time.oneOf[0].properties.clock`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "相对时间起点的共享名称；仅对确实共用起点的数据填写同一个值，省略不自动同步。"
}
```

## `$.properties.sources.items.oneOf[1].properties.time.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "time_type",
    "unit"
  ],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[1].properties.time.oneOf[1].properties.unit`

```json
{
  "enum": [
    "s",
    "ms",
    "us",
    "ns",
    "ISO8601"
  ],
  "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。可选值：\"s\"：秒；\"ms\"：毫秒；\"us\"：微秒；\"ns\"：纳秒；\"ISO8601\"：包含日期和时区依据的时间文本。"
}
```

## `$.properties.sources.items.oneOf[1].properties.time.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "应用到来源时间的固定偏移，可正可负，必须带s/ms/us/ns单位；不是时区或日期。",
  "default": "0s"
}
```

## `$.properties.sources.items.oneOf[1].properties.time.oneOf[1].properties.timezone`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "绝对时间缺少自身时区时采用的明确时区，例如UTC或IANA名称；不读取机器默认时区作为配置。"
}
```

## `$.properties.sources.items.oneOf[1].properties.time.oneOf[1].properties.time_type`

```json
{
  "const": "absolute",
  "description": "时间坐标类型：相对公共起点，或带时区依据的绝对时间。 固定值：\"absolute\"（有时区依据的绝对时间）。"
}
```

## `$.properties.sources.items.oneOf[1].properties.metadata`

```json
{
  "type": "object",
  "additionalProperties": true,
  "description": "附加说明对象；允许自定义JSON原生值，但不参与隐藏转换、模板执行或业务参数推断。"
}
```

## `$.properties.sources.items.oneOf[1].properties.path`

```json
{
  "description": "输入文件、目录或通配符，支持单项及列表。path和paths不能同时填写。"
}
```

## `$.properties.sources.items.oneOf[1].properties.path.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[1].properties.path.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[1].properties.path.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[1].properties.path.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[1].properties.path.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "保持声明顺序的路径列表；各目录匹配集合内部自然排序。"
}
```

## `$.properties.sources.items.oneOf[1].properties.path.oneOf[2].items`

```json
{
  "description": "路径文字，或带自身offset的文件声明。"
}
```

## `$.properties.sources.items.oneOf[1].properties.path.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[1].properties.path.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[1].properties.path.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[1].properties.path.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[1].properties.paths`

```json
{
  "description": "输入文件、目录或通配符，支持单项及列表。path和paths不能同时填写。"
}
```

## `$.properties.sources.items.oneOf[1].properties.paths.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[1].properties.paths.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[1].properties.paths.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[1].properties.paths.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[1].properties.paths.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "保持声明顺序的路径列表；各目录匹配集合内部自然排序。"
}
```

## `$.properties.sources.items.oneOf[1].properties.paths.oneOf[2].items`

```json
{
  "description": "路径文字，或带自身offset的文件声明。"
}
```

## `$.properties.sources.items.oneOf[1].properties.paths.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[1].properties.paths.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[1].properties.paths.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[1].properties.paths.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[1].properties.time_column`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "已解码信号CSV的时间列名，按来源time的单位和坐标解释。"
}
```

## `$.properties.sources.items.oneOf[1].properties.source_type`

```json
{
  "const": "signal_csv",
  "description": "数据来源类型，决定使用哪个读取器及其必需字段。 固定值：\"signal_csv\"（已解码信号CSV）。"
}
```

## `$.properties.sources.items.oneOf[1].properties.reader`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "与本来源格式有关的读取、文本解析和解码选项；省略适用参数时采用已说明的默认值。"
}
```

## `$.properties.sources.items.oneOf[1].properties.reader.properties.encoding`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "输入文本编码。用于真实读取；静态检查不据此判断文件可读。 已解码CSV默认utf-8-sig，兼容文件开头带BOM或不带BOM的UTF-8；显式编码优先，不删除文件中间的U+FEFF字符。",
  "default": "utf-8-sig"
}
```

## `$.properties.sources.items.oneOf[1].properties.reader.properties.delimiter`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 1,
  "pattern": "^[^\\r\\n]$",
  "description": "已解码信号CSV的单字符分隔符，不能使用换行符。",
  "default": ","
}
```

## `$.properties.sources.items.oneOf[1].properties.reader.properties.missing_values`

```json
{
  "type": "array",
  "uniqueItems": true,
  "description": "显式视为缺失的文本列表；缺失不会自动转换为零。",
  "default": [
    ""
  ]
}
```

## `$.properties.sources.items.oneOf[1].properties.reader.properties.missing_values.items`

```json
{
  "type": "string"
}
```

## `$.properties.sources.items.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "source_type",
    "dbc_by_channel"
  ],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[2].oneOf[0]`

```json
{
  "required": [
    "path"
  ],
  "not": {
    "required": [
      "paths"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[2].oneOf[1]`

```json
{
  "required": [
    "paths"
  ],
  "not": {
    "required": [
      "path"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[2].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "来源在本计划内的名称；省略时按声明位置生成source_1、source_2等。后续source引用使用此名称，不用于猜测原字段或同步。"
}
```

## `$.properties.sources.items.oneOf[2].properties.time`

```json
{
  "description": "来源时间的类型、单位、时钟和偏移设置。time_type省略为relative，clock省略生成来源独立起点；只有有同步依据的多来源才填写共同clock。"
}
```

## `$.properties.sources.items.oneOf[2].properties.time.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[2].properties.time.oneOf[0].properties.unit`

```json
{
  "const": "s",
  "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。 固定值：\"s\"（秒）。"
}
```

## `$.properties.sources.items.oneOf[2].properties.time.oneOf[0].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "应用到来源时间的固定偏移，可正可负，必须带s/ms/us/ns单位；不是时区或日期。",
  "default": "0s"
}
```

## `$.properties.sources.items.oneOf[2].properties.time.oneOf[0].properties.time_type`

```json
{
  "const": "relative",
  "description": "时间坐标类型：相对公共起点，或带时区依据的绝对时间。 固定值：\"relative\"（相对明确公共起点的时间）。"
}
```

## `$.properties.sources.items.oneOf[2].properties.time.oneOf[0].properties.clock`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "相对时间起点的共享名称；仅对确实共用起点的数据填写同一个值，省略不自动同步。"
}
```

## `$.properties.sources.items.oneOf[2].properties.time.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "time_type"
  ],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[2].properties.time.oneOf[1].properties.unit`

```json
{
  "const": "s",
  "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。 固定值：\"s\"（秒）。"
}
```

## `$.properties.sources.items.oneOf[2].properties.time.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "应用到来源时间的固定偏移，可正可负，必须带s/ms/us/ns单位；不是时区或日期。",
  "default": "0s"
}
```

## `$.properties.sources.items.oneOf[2].properties.time.oneOf[1].properties.time_type`

```json
{
  "const": "absolute",
  "description": "时间坐标类型：相对公共起点，或带时区依据的绝对时间。 固定值：\"absolute\"（有时区依据的绝对时间）。"
}
```

## `$.properties.sources.items.oneOf[2].properties.legacy_profile`

```json
{
  "const": "sclicer-functions-v1",
  "description": "BLF既有读取/解码实现标识，可省略，默认sclicer-functions-v1；显式提供时只接受该已接入实现。"
}
```

## `$.properties.sources.items.oneOf[2].properties.path`

```json
{
  "description": "输入文件、目录或通配符，支持单项及列表。path和paths不能同时填写。"
}
```

## `$.properties.sources.items.oneOf[2].properties.path.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[2].properties.path.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[2].properties.path.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[2].properties.path.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[2].properties.path.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "保持声明顺序的路径列表；各目录匹配集合内部自然排序。"
}
```

## `$.properties.sources.items.oneOf[2].properties.path.oneOf[2].items`

```json
{
  "description": "路径文字，或带自身offset的文件声明。"
}
```

## `$.properties.sources.items.oneOf[2].properties.path.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[2].properties.path.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[2].properties.path.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[2].properties.path.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[2].properties.paths`

```json
{
  "description": "输入文件、目录或通配符，支持单项及列表。path和paths不能同时填写。"
}
```

## `$.properties.sources.items.oneOf[2].properties.paths.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[2].properties.paths.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[2].properties.paths.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[2].properties.paths.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[2].properties.paths.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "保持声明顺序的路径列表；各目录匹配集合内部自然排序。"
}
```

## `$.properties.sources.items.oneOf[2].properties.paths.oneOf[2].items`

```json
{
  "description": "路径文字，或带自身offset的文件声明。"
}
```

## `$.properties.sources.items.oneOf[2].properties.paths.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[2].properties.paths.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[2].properties.paths.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[2].properties.paths.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[2].properties.dbc_by_channel`

```json
{
  "type": "object",
  "minProperties": 1,
  "maxProperties": 1,
  "propertyNames": {
    "pattern": "^[1-9][0-9]*(?![\\s\\S])"
  },
  "additionalProperties": {
    "type": "string",
    "minLength": 1,
    "pattern": "\\S"
  },
  "description": "唯一目标通道到DBC文件的显式映射；通道键使用从1开始、无前导零的正整数文本，DBC路径按声明文件定位。"
}
```

## `$.properties.sources.items.oneOf[2].properties.metadata`

```json
{
  "type": "object",
  "additionalProperties": true,
  "description": "附加说明对象；允许自定义JSON原生值，但不参与隐藏转换、模板执行或业务参数推断。"
}
```

## `$.properties.sources.items.oneOf[2].properties.source_type`

```json
{
  "const": "can_blf",
  "description": "数据来源类型，决定使用哪个读取器及其必需字段。 固定值：\"can_blf\"（原始CAN二进制BLF）。"
}
```

## `$.properties.sources.items.oneOf[2].properties.reader`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "与本来源格式有关的读取、文本解析和解码选项；省略适用参数时采用已说明的默认值。"
}
```

## `$.properties.sources.items.oneOf[2].properties.reader.properties.decode_policy`

```json
{
  "enum": [
    "strict",
    "partial",
    "legacy"
  ],
  "default": "strict",
  "description": "已选CAN报文的载荷长度检查政策，默认strict。strict：实际载荷与DBC长度相同，且DLC与字节数一致；partial：允许载荷短于DBC，但不能超过DBC长度或出现DLC与实际字节数不一致，实际解码仍沿现有实现；legacy：保留原实现的解码调用和长度处理。"
}
```

## `$.properties.sources.items.oneOf[2].properties.reader.properties.decode_scope`

```json
{
  "type": "string",
  "enum": [
    "all",
    "requested"
  ],
  "default": "requested",
  "description": "CAN解码尝试范围。默认requested，只解码当前分析需要的报文/字段；all扩大尝试解码的范围。对纯BLF串行接续，strict/partial跳过远程帧和错误帧。all不保证每帧有DBC定义、解码成功或生成逐帧诊断；选择all本身不要求填写dataset.domain。文件并行和time_order只支持requested。"
}
```

## `$.properties.sources.items.oneOf[2].properties.reader.properties.input_check`

```json
{
  "type": "string",
  "enum": [
    "auto",
    "full"
  ],
  "default": "auto",
  "description": "CAN输入检查范围。auto按消费者选择必要检查，full检查全部原帧和时间，不强制解码无关信号。可选值：\"auto\"：按实际消费者选择必要检查；\"full\"：检查全部原帧和时间。"
}
```

## `$.properties.sources.items.oneOf[2].properties.file_merge`

```json
{
  "enum": [
    "concatenate",
    "time_order"
  ],
  "default": "concatenate",
  "description": "控制同一来源的多个文件如何衔接。concatenate按paths顺序读取，仅在任务要求检查的时间范围内拒绝回退；time_order要求各文件中参与排序的记录时间有序，按记录时间、文件位置、原记录顺序稳定归并。保留重叠报文，不自动平移时间或去重。该选择与进程数无关。"
}
```

## `$.properties.sources.items.oneOf[3]`

```json
{
  "type": "object",
  "required": [
    "source_type",
    "dbc_by_channel"
  ],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[3].oneOf[0]`

```json
{
  "required": [
    "path"
  ],
  "not": {
    "required": [
      "paths"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[3].oneOf[1]`

```json
{
  "required": [
    "paths"
  ],
  "not": {
    "required": [
      "path"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[3].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "来源在本计划内的名称；省略时按声明位置生成source_1、source_2等。后续source引用使用此名称，不用于猜测原字段或同步。"
}
```

## `$.properties.sources.items.oneOf[3].properties.time`

```json
{
  "description": "来源时间的类型、单位、时钟和偏移设置。time_type省略为relative，clock省略生成来源独立起点；只有有同步依据的多来源才填写共同clock。"
}
```

## `$.properties.sources.items.oneOf[3].properties.time.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[3].properties.time.oneOf[0].properties.unit`

```json
{
  "const": "s",
  "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。 固定值：\"s\"（秒）。"
}
```

## `$.properties.sources.items.oneOf[3].properties.time.oneOf[0].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "应用到来源时间的固定偏移，可正可负，必须带s/ms/us/ns单位；不是时区或日期。",
  "default": "0s"
}
```

## `$.properties.sources.items.oneOf[3].properties.time.oneOf[0].properties.time_type`

```json
{
  "const": "relative",
  "description": "时间坐标类型：相对公共起点，或带时区依据的绝对时间。 固定值：\"relative\"（相对明确公共起点的时间）。"
}
```

## `$.properties.sources.items.oneOf[3].properties.time.oneOf[0].properties.clock`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "相对时间起点的共享名称；仅对确实共用起点的数据填写同一个值，省略不自动同步。"
}
```

## `$.properties.sources.items.oneOf[3].properties.time.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "time_type"
  ],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[3].properties.time.oneOf[1].properties.unit`

```json
{
  "const": "s",
  "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。 固定值：\"s\"（秒）。"
}
```

## `$.properties.sources.items.oneOf[3].properties.time.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "应用到来源时间的固定偏移，可正可负，必须带s/ms/us/ns单位；不是时区或日期。",
  "default": "0s"
}
```

## `$.properties.sources.items.oneOf[3].properties.time.oneOf[1].properties.time_type`

```json
{
  "const": "absolute",
  "description": "时间坐标类型：相对公共起点，或带时区依据的绝对时间。 固定值：\"absolute\"（有时区依据的绝对时间）。"
}
```

## `$.properties.sources.items.oneOf[3].properties.time.oneOf[1].properties.timezone`

```json
{
  "type": "string",
  "description": "采集时间的固定时区，填写UTC或带符号小时分钟，例如+08:00。"
}
```

## `$.properties.sources.items.oneOf[3].properties.path`

```json
{
  "description": "输入文件、目录或通配符，支持单项及列表。path和paths不能同时填写。"
}
```

## `$.properties.sources.items.oneOf[3].properties.path.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[3].properties.path.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[3].properties.path.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[3].properties.path.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[3].properties.path.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "保持声明顺序的路径列表；各目录匹配集合内部自然排序。"
}
```

## `$.properties.sources.items.oneOf[3].properties.path.oneOf[2].items`

```json
{
  "description": "路径文字，或带自身offset的文件声明。"
}
```

## `$.properties.sources.items.oneOf[3].properties.path.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[3].properties.path.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[3].properties.path.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[3].properties.path.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[3].properties.paths`

```json
{
  "description": "输入文件、目录或通配符，支持单项及列表。path和paths不能同时填写。"
}
```

## `$.properties.sources.items.oneOf[3].properties.paths.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[3].properties.paths.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[3].properties.paths.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[3].properties.paths.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[3].properties.paths.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "保持声明顺序的路径列表；各目录匹配集合内部自然排序。"
}
```

## `$.properties.sources.items.oneOf[3].properties.paths.oneOf[2].items`

```json
{
  "description": "路径文字，或带自身offset的文件声明。"
}
```

## `$.properties.sources.items.oneOf[3].properties.paths.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[3].properties.paths.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[3].properties.paths.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[3].properties.paths.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[3].properties.offsets`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "按输入文件顺序提供的时间偏移，数量须匹配文件列表，不能借偏移默默重排文件。"
}
```

## `$.properties.sources.items.oneOf[3].properties.offsets.items`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "固定时间偏移，只接受数值与s/ms/us/ns单位，不接受日期。"
}
```

## `$.properties.sources.items.oneOf[3].properties.dbc_by_channel`

```json
{
  "type": "object",
  "minProperties": 1,
  "maxProperties": 1,
  "patternProperties": {
    "^[1-9][0-9]*(?![\\s\\S])": {
      "type": "string",
      "minLength": 1
    }
  },
  "additionalProperties": false,
  "description": "唯一目标通道到DBC文件的显式映射；通道键使用从1开始、无前导零的正整数文本，DBC路径按声明文件定位。"
}
```

## `$.properties.sources.items.oneOf[3].properties.metadata`

```json
{
  "type": "object",
  "description": "附加说明对象；允许自定义JSON原生值，但不参与隐藏转换、模板执行或业务参数推断。"
}
```

## `$.properties.sources.items.oneOf[3].properties.source_type`

```json
{
  "const": "can_asc",
  "description": "数据来源类型，决定使用哪个读取器及其必需字段。 固定值：\"can_asc\"（原始CAN文本ASC）。"
}
```

## `$.properties.sources.items.oneOf[3].properties.reader`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "与本来源格式有关的读取、文本解析和解码选项；省略适用参数时采用已说明的默认值。"
}
```

## `$.properties.sources.items.oneOf[3].properties.reader.properties.version`

```json
{
  "enum": [
    "vector-asc-v1",
    "vector-asc-statistics-v1",
    "sclicer-asc-v1"
  ],
  "description": "选择ASC行布局。默认vector-asc-v1读取标准Vector ASC及可选的Length/BitCount/ID统计尾，字段顺序、数值和ID仍严格检查。vector-asc-statistics-v1保留显式标准统计入口；sclicer-asc-v1用于Sclicer的不同FD排列，不自动混猜。"
}
```

## `$.properties.sources.items.oneOf[3].properties.reader.properties.encoding`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "输入文本编码。用于真实读取；静态检查不据此判断文件可读。 CAN文本解析默认utf-8-sig。",
  "default": "utf-8-sig"
}
```

## `$.properties.sources.items.oneOf[3].properties.reader.properties.decode_policy`

```json
{
  "enum": [
    "strict",
    "partial",
    "legacy"
  ],
  "default": "strict",
  "description": "已选CAN报文的载荷长度检查政策，默认strict。strict：实际载荷与DBC长度相同，且DLC与字节数一致；partial：允许载荷短于DBC，但不能超过DBC长度或出现DLC与实际字节数不一致，实际解码仍沿现有实现；legacy：保留原实现的解码调用和长度处理。"
}
```

## `$.properties.sources.items.oneOf[3].properties.reader.properties.input_check`

```json
{
  "type": "string",
  "enum": [
    "auto",
    "full"
  ],
  "default": "auto",
  "description": "auto按实际消费者检查时间顺序；ASC普通分析仅检查所需通道/ID，来源范围仍取同次全部记录的最早/最晚时间。full或原帧导出检查全部记录顺序；任何模式都不自动排序或修改时间。"
}
```

## `$.properties.sources.items.oneOf[3].properties.file_merge`

```json
{
  "enum": [
    "concatenate",
    "time_order"
  ],
  "default": "concatenate",
  "description": "控制同一来源的多个文件如何衔接。concatenate按paths顺序读取，仅在任务要求检查的时间范围内拒绝回退；time_order要求各文件中参与排序的记录时间有序，按记录时间、文件位置、原记录顺序稳定归并。保留重叠报文，不自动平移时间或去重。该选择与进程数无关。"
}
```

## `$.properties.sources.items.oneOf[4]`

```json
{
  "type": "object",
  "required": [
    "source_type",
    "time",
    "dbc_by_channel",
    "reader"
  ],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[4].oneOf[0]`

```json
{
  "required": [
    "path"
  ],
  "not": {
    "required": [
      "paths"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].oneOf[1]`

```json
{
  "required": [
    "paths"
  ],
  "not": {
    "required": [
      "path"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "来源在本计划内的名称；省略时按声明位置生成source_1、source_2等。后续source引用使用此名称，不用于猜测原字段或同步。"
}
```

## `$.properties.sources.items.oneOf[4].properties.time`

```json
{
  "description": "来源时间的类型、单位、时钟和偏移设置。time_type省略为relative，clock省略生成来源独立起点；只有有同步依据的多来源才填写共同clock。"
}
```

## `$.properties.sources.items.oneOf[4].properties.time.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "unit"
  ],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[4].properties.time.oneOf[0].properties.unit`

```json
{
  "enum": [
    "s",
    "ms",
    "us",
    "ns",
    "ISO8601"
  ],
  "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。可选值：\"s\"：秒；\"ms\"：毫秒；\"us\"：微秒；\"ns\"：纳秒；\"ISO8601\"：包含日期和时区依据的时间文本。"
}
```

## `$.properties.sources.items.oneOf[4].properties.time.oneOf[0].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "应用到来源时间的固定偏移，可正可负，必须带s/ms/us/ns单位；不是时区或日期。",
  "default": "0s"
}
```

## `$.properties.sources.items.oneOf[4].properties.time.oneOf[0].properties.time_type`

```json
{
  "const": "relative",
  "description": "时间坐标类型：相对公共起点，或带时区依据的绝对时间。 固定值：\"relative\"（相对明确公共起点的时间）。"
}
```

## `$.properties.sources.items.oneOf[4].properties.time.oneOf[0].properties.clock`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "相对时间起点的共享名称；仅对确实共用起点的数据填写同一个值，省略不自动同步。"
}
```

## `$.properties.sources.items.oneOf[4].properties.time.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "time_type",
    "unit"
  ],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[4].properties.time.oneOf[1].properties.unit`

```json
{
  "enum": [
    "s",
    "ms",
    "us",
    "ns",
    "ISO8601"
  ],
  "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。可选值：\"s\"：秒；\"ms\"：毫秒；\"us\"：微秒；\"ns\"：纳秒；\"ISO8601\"：包含日期和时区依据的时间文本。"
}
```

## `$.properties.sources.items.oneOf[4].properties.time.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "应用到来源时间的固定偏移，可正可负，必须带s/ms/us/ns单位；不是时区或日期。",
  "default": "0s"
}
```

## `$.properties.sources.items.oneOf[4].properties.time.oneOf[1].properties.time_type`

```json
{
  "const": "absolute",
  "description": "时间坐标类型：相对公共起点，或带时区依据的绝对时间。 固定值：\"absolute\"（有时区依据的绝对时间）。"
}
```

## `$.properties.sources.items.oneOf[4].properties.time.oneOf[1].properties.timezone`

```json
{
  "type": "string",
  "description": "采集时间的固定时区，填写UTC或带符号小时分钟，例如+08:00。"
}
```

## `$.properties.sources.items.oneOf[4].properties.path`

```json
{
  "description": "输入文件、目录或通配符，支持单项及列表。path和paths不能同时填写。"
}
```

## `$.properties.sources.items.oneOf[4].properties.path.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[4].properties.path.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[4].properties.path.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[4].properties.path.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[4].properties.path.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "保持声明顺序的路径列表；各目录匹配集合内部自然排序。"
}
```

## `$.properties.sources.items.oneOf[4].properties.path.oneOf[2].items`

```json
{
  "description": "路径文字，或带自身offset的文件声明。"
}
```

## `$.properties.sources.items.oneOf[4].properties.path.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[4].properties.path.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[4].properties.path.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[4].properties.path.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[4].properties.paths`

```json
{
  "description": "输入文件、目录或通配符，支持单项及列表。path和paths不能同时填写。"
}
```

## `$.properties.sources.items.oneOf[4].properties.paths.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[4].properties.paths.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[4].properties.paths.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[4].properties.paths.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[4].properties.paths.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "保持声明顺序的路径列表；各目录匹配集合内部自然排序。"
}
```

## `$.properties.sources.items.oneOf[4].properties.paths.oneOf[2].items`

```json
{
  "description": "路径文字，或带自身offset的文件声明。"
}
```

## `$.properties.sources.items.oneOf[4].properties.paths.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[4].properties.paths.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[4].properties.paths.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[4].properties.paths.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[4].properties.offsets`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "按输入文件顺序提供的时间偏移，数量须匹配文件列表，不能借偏移默默重排文件。"
}
```

## `$.properties.sources.items.oneOf[4].properties.offsets.items`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "固定时间偏移，只接受数值与s/ms/us/ns单位，不接受日期。"
}
```

## `$.properties.sources.items.oneOf[4].properties.dbc_by_channel`

```json
{
  "type": "object",
  "minProperties": 1,
  "maxProperties": 1,
  "patternProperties": {
    "^[1-9][0-9]*(?![\\s\\S])": {
      "type": "string",
      "minLength": 1
    }
  },
  "additionalProperties": false,
  "description": "唯一目标通道到DBC文件的显式映射；通道键使用从1开始、无前导零的正整数文本，DBC路径按声明文件定位。"
}
```

## `$.properties.sources.items.oneOf[4].properties.metadata`

```json
{
  "type": "object",
  "description": "附加说明对象；允许自定义JSON原生值，但不参与隐藏转换、模板执行或业务参数推断。"
}
```

## `$.properties.sources.items.oneOf[4].properties.source_type`

```json
{
  "const": "raw_can_csv",
  "description": "数据来源类型，决定使用哪个读取器及其必需字段。 固定值：\"raw_can_csv\"（显式布局的原始CAN帧CSV）。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader`

```json
{
  "type": "object",
  "required": [
    "layout",
    "time_format"
  ],
  "additionalProperties": false,
  "description": "与本来源格式有关的读取、文本解析和解码选项；省略适用参数时采用已说明的默认值。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout`

```json
{
  "type": "object",
  "required": [
    "fields"
  ],
  "additionalProperties": false,
  "description": "原始CAN CSV的字段布局，显式说明分隔符、列/固定值映射、时间和数值表示。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields`

```json
{
  "type": "object",
  "required": [
    "timestamp",
    "frame_id",
    "data"
  ],
  "additionalProperties": false,
  "description": "原始CAN语义字段到输入列或固定值的显式映射。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp`

```json
{
  "description": "报文时间字段的列或固定值映射，按time_format和来源时间声明转换。 可直接填写列名或从1开始的列号；固定值仍用fixed对象。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "报文时间字段的列或固定值映射，按time_format和来源时间声明转换。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ],
  "not": {
    "required": [
      "fixed"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ],
  "not": {
    "required": [
      "column"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.column`

```json
{
  "description": "读取的列名或列索引，与fixed二选一；必须与has_header及实际布局一致。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.fixed`

```json
{
  "description": "该语义字段的显式固定值，与column二选一；不是缺失时的自动补值。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "是否清除输入字段两侧空白，不改变中间字符。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "additionalProperties": {
    "oneOf": [
      {
        "type": "string",
        "maxLength": 256
      },
      {
        "type": "integer",
        "minimum": -9223372036854775808,
        "maximum": 18446744073709551615
      },
      {
        "type": "boolean"
      }
    ]
  },
  "maxProperties": 256,
  "description": "可省略或null表示不映射；对象须有1至256项，原文本键和字符串目标均不超过256字符。与fixed的文本长度限制不同。",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.timestamp.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id`

```json
{
  "description": "CAN报文仲裁ID的列或固定值映射，按id_base解释。 可直接填写列名或从1开始的列号；固定值仍用fixed对象。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "CAN报文仲裁ID的列或固定值映射，按id_base解释。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ],
  "not": {
    "required": [
      "fixed"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ],
  "not": {
    "required": [
      "column"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.column`

```json
{
  "description": "读取的列名或列索引，与fixed二选一；必须与has_header及实际布局一致。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.fixed`

```json
{
  "description": "该语义字段的显式固定值，与column二选一；不是缺失时的自动补值。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "是否清除输入字段两侧空白，不改变中间字符。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "additionalProperties": {
    "oneOf": [
      {
        "type": "string",
        "maxLength": 256
      },
      {
        "type": "integer",
        "minimum": -9223372036854775808,
        "maximum": 18446744073709551615
      },
      {
        "type": "boolean"
      }
    ]
  },
  "maxProperties": 256,
  "description": "可省略或null表示不映射；对象须有1至256项，原文本键和字符串目标均不超过256字符。与fixed的文本长度限制不同。",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_id.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel`

```json
{
  "description": "原始CSV通道列映射，固定值保持文件编号；channel_origin指定文件从0或1开始。 可直接填写列名或从1开始的列号；固定值仍用fixed对象。 省略时继承来源唯一DBC通道。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "原始CSV通道列映射，固定值保持文件编号；channel_origin指定文件从0或1开始。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ],
  "not": {
    "required": [
      "fixed"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ],
  "not": {
    "required": [
      "column"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.column`

```json
{
  "description": "读取的列名或列索引，与fixed二选一；必须与has_header及实际布局一致。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.fixed`

```json
{
  "description": "该语义字段的显式固定值，与column二选一；不是缺失时的自动补值。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "是否清除输入字段两侧空白，不改变中间字符。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "additionalProperties": {
    "oneOf": [
      {
        "type": "string",
        "maxLength": 256
      },
      {
        "type": "integer",
        "minimum": -9223372036854775808,
        "maximum": 18446744073709551615
      },
      {
        "type": "boolean"
      }
    ]
  },
  "maxProperties": 256,
  "description": "可省略或null表示不映射；对象须有1至256项，原文本键和字符串目标均不超过256字符。与fixed的文本长度限制不同。",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.channel.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx`

```json
{
  "description": "接收/发送方向的输入映射，值必须能明确解释为方向标志。 可直接填写列名或从1开始的列号；固定值仍用fixed对象。 可省略；省略时方向未知，仅原帧导出或重建需要补充。Rx/Tx、接收/发送可直接识别。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "接收/发送方向的输入映射，值必须能明确解释为方向标志。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ],
  "not": {
    "required": [
      "fixed"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ],
  "not": {
    "required": [
      "column"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.column`

```json
{
  "description": "读取的列名或列索引，与fixed二选一；必须与has_header及实际布局一致。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.fixed`

```json
{
  "description": "该语义字段的显式固定值，与column二选一；不是缺失时的自动补值。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "是否清除输入字段两侧空白，不改变中间字符。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "additionalProperties": {
    "oneOf": [
      {
        "type": "string",
        "maxLength": 256
      },
      {
        "type": "integer",
        "minimum": -9223372036854775808,
        "maximum": 18446744073709551615
      },
      {
        "type": "boolean"
      }
    ]
  },
  "maxProperties": 256,
  "description": "可省略或null表示不映射；对象须有1至256项，原文本键和字符串目标均不超过256字符。与fixed的文本长度限制不同。",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_rx.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended`

```json
{
  "description": "可选原始帧类型列或常量；有列时以真实字段为准。省略后由本次绑定与DBC唯一识别，不能识别时要求补充。小ID不能单独证明标准帧。 可直接填写列名或从1开始的列号；固定值仍用fixed对象。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "可选原始帧类型列或常量；有列时以真实字段为准。省略后由本次绑定与DBC唯一识别，不能识别时要求补充。小ID不能单独证明标准帧。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ],
  "not": {
    "required": [
      "fixed"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ],
  "not": {
    "required": [
      "column"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.column`

```json
{
  "description": "读取的列名或列索引，与fixed二选一；必须与has_header及实际布局一致。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.fixed`

```json
{
  "description": "该语义字段的显式固定值，与column二选一；不是缺失时的自动补值。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "是否清除输入字段两侧空白，不改变中间字符。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "additionalProperties": {
    "oneOf": [
      {
        "type": "string",
        "maxLength": 256
      },
      {
        "type": "integer",
        "minimum": -9223372036854775808,
        "maximum": 18446744073709551615
      },
      {
        "type": "boolean"
      }
    ]
  },
  "maxProperties": 256,
  "description": "可省略或null表示不映射；对象须有1至256项，原文本键和字符串目标均不超过256字符。与fixed的文本长度限制不同。",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_extended.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd`

```json
{
  "description": "可选CAN/FD列或常量；有列时以真实字段为准。省略后按绑定及DBC识别；DBC声明FD仍可能是实际经典CAN，无法唯一判断时必须补充，不按短载荷猜测。 可直接填写列名或从1开始的列号；固定值仍用fixed对象。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "可选CAN/FD列或常量；有列时以真实字段为准。省略后按绑定及DBC识别；DBC声明FD仍可能是实际经典CAN，无法唯一判断时必须补充，不按短载荷猜测。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ],
  "not": {
    "required": [
      "fixed"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ],
  "not": {
    "required": [
      "column"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.column`

```json
{
  "description": "读取的列名或列索引，与fixed二选一；必须与has_header及实际布局一致。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.fixed`

```json
{
  "description": "该语义字段的显式固定值，与column二选一；不是缺失时的自动补值。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "是否清除输入字段两侧空白，不改变中间字符。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "additionalProperties": {
    "oneOf": [
      {
        "type": "string",
        "maxLength": 256
      },
      {
        "type": "integer",
        "minimum": -9223372036854775808,
        "maximum": 18446744073709551615
      },
      {
        "type": "boolean"
      }
    ]
  },
  "maxProperties": 256,
  "description": "可省略或null表示不映射；对象须有1至256项，原文本键和字符串目标均不超过256字符。与fixed的文本长度限制不同。",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.is_fd.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind`

```json
{
  "description": "CAN帧种类的输入映射，用于区分数据、远程或错误帧等已支持格式。 可直接填写列名或从1开始的列号；固定值仍用fixed对象。 省略时为普通数据帧；远程或错误帧须显式提供。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "CAN帧种类的输入映射，用于区分数据、远程或错误帧等已支持格式。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ],
  "not": {
    "required": [
      "fixed"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ],
  "not": {
    "required": [
      "column"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.column`

```json
{
  "description": "读取的列名或列索引，与fixed二选一；必须与has_header及实际布局一致。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.fixed`

```json
{
  "description": "该语义字段的显式固定值，与column二选一；不是缺失时的自动补值。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "是否清除输入字段两侧空白，不改变中间字符。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "additionalProperties": {
    "oneOf": [
      {
        "type": "string",
        "maxLength": 256
      },
      {
        "type": "integer",
        "minimum": -9223372036854775808,
        "maximum": 18446744073709551615
      },
      {
        "type": "boolean"
      }
    ]
  },
  "maxProperties": 256,
  "description": "可省略或null表示不映射；对象须有1至256项，原文本键和字符串目标均不超过256字符。与fixed的文本长度限制不同。",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.frame_kind.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data`

```json
{
  "description": "CAN负载字节的输入映射，按payload_style解析，不把缺少负载补成零。 可直接填写列名或从1开始的列号；固定值仍用fixed对象。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "CAN负载字节的输入映射，按payload_style解析，不把缺少负载补成零。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ],
  "not": {
    "required": [
      "fixed"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ],
  "not": {
    "required": [
      "column"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.column`

```json
{
  "description": "读取的列名或列索引，与fixed二选一；必须与has_header及实际布局一致。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.fixed`

```json
{
  "description": "该语义字段的显式固定值，与column二选一；不是缺失时的自动补值。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "是否清除输入字段两侧空白，不改变中间字符。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "additionalProperties": {
    "oneOf": [
      {
        "type": "string",
        "maxLength": 256
      },
      {
        "type": "integer",
        "minimum": -9223372036854775808,
        "maximum": 18446744073709551615
      },
      {
        "type": "boolean"
      }
    ]
  },
  "maxProperties": 256,
  "description": "可省略或null表示不映射；对象须有1至256项，原文本键和字符串目标均不超过256字符。与fixed的文本长度限制不同。",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.data.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length`

```json
{
  "description": "实际负载字节数的输入映射，与DLC编码区别处理。 可直接填写列名或从1开始的列号；固定值仍用fixed对象。 省略时按数据字节数推导。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "实际负载字节数的输入映射，与DLC编码区别处理。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ],
  "not": {
    "required": [
      "fixed"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ],
  "not": {
    "required": [
      "column"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.column`

```json
{
  "description": "读取的列名或列索引，与fixed二选一；必须与has_header及实际布局一致。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.fixed`

```json
{
  "description": "该语义字段的显式固定值，与column二选一；不是缺失时的自动补值。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "是否清除输入字段两侧空白，不改变中间字符。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "additionalProperties": {
    "oneOf": [
      {
        "type": "string",
        "maxLength": 256
      },
      {
        "type": "integer",
        "minimum": -9223372036854775808,
        "maximum": 18446744073709551615
      },
      {
        "type": "boolean"
      }
    ]
  },
  "maxProperties": 256,
  "description": "可省略或null表示不映射；对象须有1至256项，原文本键和字符串目标均不超过256字符。与fixed的文本长度限制不同。",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.payload_length.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code`

```json
{
  "description": "CAN DLC编码的输入映射；CAN FD的DLC编码不等同于字节数。 可直接填写列名或从1开始的列号；固定值仍用fixed对象。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "CAN DLC编码的输入映射；CAN FD的DLC编码不等同于字节数。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ],
  "not": {
    "required": [
      "fixed"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ],
  "not": {
    "required": [
      "column"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.column`

```json
{
  "description": "读取的列名或列索引，与fixed二选一；必须与has_header及实际布局一致。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.fixed`

```json
{
  "description": "该语义字段的显式固定值，与column二选一；不是缺失时的自动补值。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "是否清除输入字段两侧空白，不改变中间字符。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "additionalProperties": {
    "oneOf": [
      {
        "type": "string",
        "maxLength": 256
      },
      {
        "type": "integer",
        "minimum": -9223372036854775808,
        "maximum": 18446744073709551615
      },
      {
        "type": "boolean"
      }
    ]
  },
  "maxProperties": 256,
  "description": "可省略或null表示不映射；对象须有1至256项，原文本键和字符串目标均不超过256字符。与fixed的文本长度限制不同。",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.dlc_code.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch`

```json
{
  "description": "CAN FD是否切换位速率的输入映射。 可直接填写列名或从1开始的列号；固定值仍用fixed对象。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "CAN FD是否切换位速率的输入映射。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ],
  "not": {
    "required": [
      "fixed"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ],
  "not": {
    "required": [
      "column"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.column`

```json
{
  "description": "读取的列名或列索引，与fixed二选一；必须与has_header及实际布局一致。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.fixed`

```json
{
  "description": "该语义字段的显式固定值，与column二选一；不是缺失时的自动补值。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "是否清除输入字段两侧空白，不改变中间字符。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "additionalProperties": {
    "oneOf": [
      {
        "type": "string",
        "maxLength": 256
      },
      {
        "type": "integer",
        "minimum": -9223372036854775808,
        "maximum": 18446744073709551615
      },
      {
        "type": "boolean"
      }
    ]
  },
  "maxProperties": 256,
  "description": "可省略或null表示不映射；对象须有1至256项，原文本键和字符串目标均不超过256字符。与fixed的文本长度限制不同。",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.bitrate_switch.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator`

```json
{
  "description": "CAN FD错误状态标志的输入映射。 可直接填写列名或从1开始的列号；固定值仍用fixed对象。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "CAN FD错误状态标志的输入映射。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].oneOf[0]`

```json
{
  "required": [
    "column"
  ],
  "not": {
    "required": [
      "fixed"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].oneOf[1]`

```json
{
  "required": [
    "fixed"
  ],
  "not": {
    "required": [
      "column"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.column`

```json
{
  "description": "读取的列名或列索引，与fixed二选一；必须与has_header及实际布局一致。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.column.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.column.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.fixed`

```json
{
  "description": "该语义字段的显式固定值，与column二选一；不是缺失时的自动补值。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.fixed.oneOf[0]`

```json
{
  "type": "string",
  "maxLength": 16384
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.fixed.oneOf[1]`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.fixed.oneOf[2]`

```json
{
  "type": "boolean"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.strip`

```json
{
  "type": "boolean",
  "description": "是否清除输入字段两侧空白，不改变中间字符。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[0].properties.value_map`

```json
{
  "type": [
    "object",
    "null"
  ],
  "additionalProperties": {
    "oneOf": [
      {
        "type": "string",
        "maxLength": 256
      },
      {
        "type": "integer",
        "minimum": -9223372036854775808,
        "maximum": 18446744073709551615
      },
      {
        "type": "boolean"
      }
    ]
  },
  "maxProperties": 256,
  "description": "可省略或null表示不映射；对象须有1至256项，原文本键和字符串目标均不超过256字符。与fixed的文本长度限制不同。",
  "minProperties": 1,
  "propertyNames": {
    "maxLength": 256
  }
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[1]`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 256
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.fields.properties.error_state_indicator.oneOf[2]`

```json
{
  "type": "integer",
  "minimum": 1,
  "maximum": 4096
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.encoding`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "输入文本编码。用于真实读取；静态检查不据此判断文件可读。 CAN文本解析默认utf-8-sig。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.delimiter`

```json
{
  "type": "string",
  "minLength": 1,
  "maxLength": 1,
  "description": "原始CAN CSV的分隔符，必须与文件实际格式一致。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.has_header`

```json
{
  "type": "boolean",
  "description": "原始CSV是否有标题行。使用列名时需要标题，列索引则按明确布局解释。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.skip_rows`

```json
{
  "type": "integer",
  "minimum": 0,
  "description": "正式读取前跳过的行数，非负整数；用于文件中已有的说明行。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.layout.properties.layout_version`

```json
{
  "const": "raw-can-csv-layout-v1",
  "description": "原始CAN CSV字段布局的固定版本标识。 固定值：\"raw-can-csv-layout-v1\"。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.time_format`

```json
{
  "enum": [
    "numeric",
    "clock",
    "clock-ms-us-v1",
    "iso8601"
  ],
  "description": "原始CAN时间字段的文本表示方式，必须与实际文件一致。可选值：\"numeric\"：带来源单位的数值时间；\"clock\"：时分秒时钟文本；\"clock-ms-us-v1\"：旧格式的时钟/毫秒/微秒表示；\"iso8601\"：ISO 8601日期时间。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.id_base`

```json
{
  "enum": [
    "auto",
    10,
    16
  ],
  "description": "默认auto：0x前缀十六进制、0b前缀二进制、无前缀十进制。裸十六进制表可显式选择16。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.length_base`

```json
{
  "enum": [
    10,
    16
  ],
  "description": "报文长度文本的进制，支持10或16；与DLC编码是否存在分别声明。可选值：10：十进制；16：十六进制。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.channel_origin`

```json
{
  "enum": [
    0,
    1
  ],
  "description": "原始文件通道编号起点，0表示从0计数，1表示从1计数；规范化后使用0基通道。可选值：0：原文件从通道0开始编号；1：原文件从通道1开始编号。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.payload_style`

```json
{
  "enum": [
    "spaced",
    "contiguous"
  ],
  "description": "报文数据字节的文本排列方式：用空格分隔，或连续十六进制文本。可选值：\"spaced\"：字节之间用空格分隔；\"contiguous\"：连续十六进制字节文本。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.rollover_min_drop`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "允许识别跨日回绕的最小时间下降量，必须带单位；不能把任意乱序当作跨日。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.decode_policy`

```json
{
  "enum": [
    "strict",
    "partial",
    "legacy"
  ],
  "default": "strict",
  "description": "已选CAN报文的载荷长度检查政策，默认strict。strict：实际载荷与DBC长度相同，且DLC与字节数一致；partial：允许载荷短于DBC，但不能超过DBC长度或出现DLC与实际字节数不一致，实际解码仍沿现有实现；legacy：保留原实现的解码调用和长度处理。"
}
```

## `$.properties.sources.items.oneOf[4].properties.reader.properties.input_check`

```json
{
  "type": "string",
  "enum": [
    "auto",
    "full"
  ],
  "default": "auto",
  "description": "auto按实际消费者检查时间顺序；ASC普通分析仅检查所需通道/ID，来源范围仍取同次全部记录的最早/最晚时间。full或原帧导出检查全部记录顺序；任何模式都不自动排序或修改时间。"
}
```

## `$.properties.sources.items.oneOf[5]`

```json
{
  "type": "object",
  "required": [
    "dbc_by_channel"
  ],
  "additionalProperties": false,
  "description": "自动选择ASC或BLF读取；格式特有参数由实际来源检查。"
}
```

## `$.properties.sources.items.oneOf[5].oneOf[0]`

```json
{
  "required": [
    "path"
  ],
  "not": {
    "required": [
      "paths"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[5].oneOf[1]`

```json
{
  "required": [
    "paths"
  ],
  "not": {
    "required": [
      "path"
    ]
  }
}
```

## `$.properties.sources.items.oneOf[5].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "来源在本计划内的名称；省略时按声明位置生成source_1、source_2等。后续source引用使用此名称，不用于猜测原字段或同步。"
}
```

## `$.properties.sources.items.oneOf[5].properties.time`

```json
{
  "description": "来源时间的类型、单位、时钟和偏移设置。time_type省略为relative，clock省略生成来源独立起点；只有有同步依据的多来源才填写共同clock。"
}
```

## `$.properties.sources.items.oneOf[5].properties.time.oneOf[0]`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[5].properties.time.oneOf[0].properties.unit`

```json
{
  "const": "s",
  "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。 固定值：\"s\"（秒）。"
}
```

## `$.properties.sources.items.oneOf[5].properties.time.oneOf[0].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "应用到来源时间的固定偏移，可正可负，必须带s/ms/us/ns单位；不是时区或日期。",
  "default": "0s"
}
```

## `$.properties.sources.items.oneOf[5].properties.time.oneOf[0].properties.time_type`

```json
{
  "const": "relative",
  "description": "时间坐标类型：相对公共起点，或带时区依据的绝对时间。 固定值：\"relative\"（相对明确公共起点的时间）。"
}
```

## `$.properties.sources.items.oneOf[5].properties.time.oneOf[0].properties.clock`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "相对时间起点的共享名称；仅对确实共用起点的数据填写同一个值，省略不自动同步。"
}
```

## `$.properties.sources.items.oneOf[5].properties.time.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "time_type"
  ],
  "additionalProperties": false
}
```

## `$.properties.sources.items.oneOf[5].properties.time.oneOf[1].properties.unit`

```json
{
  "const": "s",
  "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。 固定值：\"s\"（秒）。"
}
```

## `$.properties.sources.items.oneOf[5].properties.time.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "应用到来源时间的固定偏移，可正可负，必须带s/ms/us/ns单位；不是时区或日期。",
  "default": "0s"
}
```

## `$.properties.sources.items.oneOf[5].properties.time.oneOf[1].properties.time_type`

```json
{
  "const": "absolute",
  "description": "时间坐标类型：相对公共起点，或带时区依据的绝对时间。 固定值：\"absolute\"（有时区依据的绝对时间）。"
}
```

## `$.properties.sources.items.oneOf[5].properties.time.oneOf[1].properties.timezone`

```json
{
  "type": "string",
  "description": "采集时间的固定时区，填写UTC或带符号小时分钟，例如+08:00。"
}
```

## `$.properties.sources.items.oneOf[5].properties.legacy_profile`

```json
{
  "const": "sclicer-functions-v1",
  "description": "BLF既有读取/解码实现标识，可省略，默认sclicer-functions-v1；显式提供时只接受该已接入实现。"
}
```

## `$.properties.sources.items.oneOf[5].properties.path`

```json
{
  "description": "输入文件、目录或通配符，支持单项及列表。path和paths不能同时填写。"
}
```

## `$.properties.sources.items.oneOf[5].properties.path.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[5].properties.path.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[5].properties.path.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[5].properties.path.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[5].properties.path.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "保持声明顺序的路径列表；各目录匹配集合内部自然排序。"
}
```

## `$.properties.sources.items.oneOf[5].properties.path.oneOf[2].items`

```json
{
  "description": "路径文字，或带自身offset的文件声明。"
}
```

## `$.properties.sources.items.oneOf[5].properties.path.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[5].properties.path.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[5].properties.path.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[5].properties.path.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[5].properties.paths`

```json
{
  "description": "输入文件、目录或通配符，支持单项及列表。path和paths不能同时填写。"
}
```

## `$.properties.sources.items.oneOf[5].properties.paths.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[5].properties.paths.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[5].properties.paths.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[5].properties.paths.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[5].properties.paths.oneOf[2]`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "保持声明顺序的路径列表；各目录匹配集合内部自然排序。"
}
```

## `$.properties.sources.items.oneOf[5].properties.paths.oneOf[2].items`

```json
{
  "description": "路径文字，或带自身offset的文件声明。"
}
```

## `$.properties.sources.items.oneOf[5].properties.paths.oneOf[2].items.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[5].properties.paths.oneOf[2].items.oneOf[1]`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "path"
  ]
}
```

## `$.properties.sources.items.oneOf[5].properties.paths.oneOf[2].items.oneOf[1].properties.path`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "本项文件、目录或通配符路径。"
}
```

## `$.properties.sources.items.oneOf[5].properties.paths.oneOf[2].items.oneOf[1].properties.offset`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "该文件的带单位时间偏移，与来源总偏移相加。"
}
```

## `$.properties.sources.items.oneOf[5].properties.dbc_by_channel`

```json
{
  "type": "object",
  "minProperties": 1,
  "maxProperties": 1,
  "propertyNames": {
    "pattern": "^[1-9][0-9]*(?![\\s\\S])"
  },
  "additionalProperties": {
    "type": "string",
    "minLength": 1,
    "pattern": "\\S"
  },
  "description": "唯一目标通道到DBC文件的显式映射；通道键使用从1开始、无前导零的正整数文本，DBC路径按声明文件定位。"
}
```

## `$.properties.sources.items.oneOf[5].properties.metadata`

```json
{
  "type": "object",
  "additionalProperties": true,
  "description": "附加说明对象；允许自定义JSON原生值，但不参与隐藏转换、模板执行或业务参数推断。"
}
```

## `$.properties.sources.items.oneOf[5].properties.source_type`

```json
{
  "enum": [
    "asc_or_blf"
  ],
  "description": "省略时按ASC/BLF扩展名识别，可在同一来源按原序混合；CSV与内存需显式选择。"
}
```

## `$.properties.sources.items.oneOf[5].properties.offsets`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "description": "按输入文件顺序提供的时间偏移，数量须匹配文件列表，不能借偏移默默重排文件。"
}
```

## `$.properties.sources.items.oneOf[5].properties.offsets.items`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "固定时间偏移，只接受数值与s/ms/us/ns单位，不接受日期。"
}
```

## `$.properties.sources.items.oneOf[5].properties.reader`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "与本来源格式有关的读取、文本解析和解码选项；省略适用参数时采用已说明的默认值。"
}
```

## `$.properties.sources.items.oneOf[5].properties.reader.properties.version`

```json
{
  "enum": [
    "vector-asc-v1",
    "vector-asc-statistics-v1",
    "sclicer-asc-v1"
  ],
  "description": "选择ASC行布局。默认vector-asc-v1读取标准Vector ASC及可选的Length/BitCount/ID统计尾，字段顺序、数值和ID仍严格检查。vector-asc-statistics-v1保留显式标准统计入口；sclicer-asc-v1用于Sclicer的不同FD排列，不自动混猜。"
}
```

## `$.properties.sources.items.oneOf[5].properties.reader.properties.encoding`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "输入文本编码。用于真实读取；静态检查不据此判断文件可读。 CAN文本解析默认utf-8-sig。",
  "default": "utf-8-sig"
}
```

## `$.properties.sources.items.oneOf[5].properties.reader.properties.decode_policy`

```json
{
  "enum": [
    "strict",
    "partial",
    "legacy"
  ],
  "default": "strict",
  "description": "已选CAN报文的载荷长度检查政策，默认strict。strict：实际载荷与DBC长度相同，且DLC与字节数一致；partial：允许载荷短于DBC，但不能超过DBC长度或出现DLC与实际字节数不一致，实际解码仍沿现有实现；legacy：保留原实现的解码调用和长度处理。"
}
```

## `$.properties.sources.items.oneOf[5].properties.reader.properties.decode_scope`

```json
{
  "type": "string",
  "enum": [
    "all",
    "requested"
  ],
  "default": "requested",
  "description": "CAN解码尝试范围。默认requested，只解码当前分析需要的报文/字段；all扩大尝试解码的范围。对纯BLF串行接续，strict/partial跳过远程帧和错误帧。all不保证每帧有DBC定义、解码成功或生成逐帧诊断；选择all本身不要求填写dataset.domain。文件并行和time_order只支持requested。"
}
```

## `$.properties.sources.items.oneOf[5].properties.reader.properties.input_check`

```json
{
  "type": "string",
  "enum": [
    "auto",
    "full"
  ],
  "default": "auto",
  "description": "auto按实际消费者检查时间顺序；ASC普通分析仅检查所需通道/ID，来源范围仍取同次全部记录的最早/最晚时间。full或原帧导出检查全部记录顺序；任何模式都不自动排序或修改时间。"
}
```

## `$.properties.sources.items.oneOf[5].properties.file_merge`

```json
{
  "enum": [
    "concatenate",
    "time_order"
  ],
  "default": "concatenate",
  "description": "控制同一来源的多个文件如何衔接。concatenate按paths顺序读取，仅在任务要求检查的时间范围内拒绝回退；time_order要求各文件中参与排序的记录时间有序，按记录时间、文件位置、原记录顺序稳定归并。保留重叠报文，不自动平移时间或去重。该选择与进程数无关。"
}
```

## `$.properties.signals`

```json
{
  "type": "array",
  "description": "把来源的原始字段绑定为分析使用的简单信号名，明确类型、单位和有效期。"
}
```

## `$.properties.signals.items.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "name",
    "field"
  ],
  "additionalProperties": false
}
```

## `$.properties.signals.items.oneOf[0].allOf[0]`

```json
{
  "if": {
    "properties": {
      "dtype": {
        "const": "enum",
        "description": "显式enum使用文字标签；CAN可从DBC补枚举表，已解析数据需提供choices。"
      }
    },
    "required": [
      "dtype"
    ]
  },
  "then": {
    "properties": {
      "choices": {
        "minItems": 1,
        "description": "枚举的[原编码,标签]二元数组；保留编码原生类型，不能用对象键把整数或布尔编码字符串化。"
      }
    },
    "allOf": [
      {
        "if": {
          "properties": {
            "field": {
              "type": "string",
              "description": "已解析信号的列名没有DBC类型和单位元数据，需由配置明确声明。"
            }
          },
          "required": [
            "field"
          ]
        },
        "then": {
          "required": [
            "choices"
          ]
        }
      }
    ]
  }
}
```

## `$.properties.signals.items.oneOf[0].allOf[1]`

```json
{
  "if": {
    "properties": {
      "field": {
        "type": "string",
        "description": "已解析信号的列名没有DBC类型和单位元数据，需由配置明确声明。"
      }
    },
    "required": [
      "field"
    ]
  },
  "then": {
    "required": [
      "dtype",
      "unit"
    ]
  }
}
```

## `$.properties.signals.items.oneOf[0].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "当前来源或信号的简单名称，供后续声明引用；不是对原数据字段的猜测或重命名。"
}
```

## `$.properties.signals.items.oneOf[0].properties.source`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "已声明来源的name。引用必须存在，不按同名字段或语义名称自动寻找来源。"
}
```

## `$.properties.signals.items.oneOf[0].properties.field`

```json
{
  "description": "来源中的真实字段。信号表/内存使用原字段名，CAN使用完整通道和报文信号定位对象。"
}
```

## `$.properties.signals.items.oneOf[0].properties.field.oneOf[0]`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S"
}
```

## `$.properties.signals.items.oneOf[0].properties.field.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "signal",
    "frame_id"
  ],
  "additionalProperties": false
}
```

## `$.properties.signals.items.oneOf[0].properties.field.oneOf[1].allOf[0]`

```json
{
  "if": {
    "properties": {
      "is_extended": {
        "const": false,
        "description": "显式选择标准帧时，整数ID不得超过11位范围。"
      }
    },
    "required": [
      "is_extended"
    ]
  },
  "then": {
    "properties": {
      "frame_id": {
        "maximum": 2047,
        "description": "标准帧的整数报文ID上限为2047；字符串转换后的范围由计划加载器核实。"
      }
    }
  }
}
```

## `$.properties.signals.items.oneOf[0].properties.field.oneOf[1].properties.channel`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "用户配置CAN通道从1开始，1对应内部0；省略时继承来源唯一通道。"
}
```

## `$.properties.signals.items.oneOf[0].properties.field.oneOf[1].properties.signal`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "DBC中该信号的原始名称，与frame_id一起定位同一报文内的信号；这里不是分析别名。"
}
```

## `$.properties.signals.items.oneOf[0].properties.field.oneOf[1].properties.frame_id`

```json
{
  "description": "CAN报文ID；整数或字符串均可。0x前缀为十六进制，0b为二进制，无前缀为十进制；解析后须在0至536870911内，显式标准帧最多2047。"
}
```

## `$.properties.signals.items.oneOf[0].properties.field.oneOf[1].properties.frame_id.oneOf[0]`

```json
{
  "type": "integer",
  "minimum": 0,
  "maximum": 536870911
}
```

## `$.properties.signals.items.oneOf[0].properties.field.oneOf[1].properties.frame_id.oneOf[1]`

```json
{
  "type": "string",
  "pattern": "^(?:[0-9]+|0[xX][0-9a-fA-F]+|0[bB][01]+)(?![\\s\\S])",
  "minLength": 1
}
```

## `$.properties.signals.items.oneOf[0].properties.field.oneOf[1].properties.is_extended`

```json
{
  "type": "boolean",
  "description": "标准／扩展帧可选约束。省略时根据DBC和实际报文识别；只有歧义时要求补充。显式null无效。"
}
```

## `$.properties.signals.items.oneOf[0].properties.field.oneOf[1].properties.is_fd`

```json
{
  "type": "boolean",
  "description": "CAN／CAN FD可选约束。省略时根据DBC和实际报文识别；只有歧义时要求补充。显式null无效。"
}
```

## `$.properties.signals.items.oneOf[0].properties.dtype`

```json
{
  "enum": [
    "int64",
    "uint64",
    "float64",
    "bool",
    "enum"
  ],
  "description": "分析信号类型：int64、uint64、float64、bool或enum。CAN省略时按DBC解码值推导数值类型，不因DBC存在枚举表自动改为enum；明确手工choices为文字或布尔标签时可确定enum或bool。已解析数据仍需声明dtype。"
}
```

## `$.properties.signals.items.oneOf[0].properties.unit`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。 CAN省略时读取DBC单位；DBC未定义则使用unknown并标为未核实，逻辑类型用1。已解析数据仍需填写。"
}
```

## `$.properties.signals.items.oneOf[0].properties.valid_for`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "有效样本最多沿用的实际时长。可省略，默认取当前信号周期的3倍；用户period优先，否则取DBC所属报文周期。均无法取得时需补充period或valid_for。显式填写覆盖默认值。",
  "examples": [
    "500ms",
    "2s"
  ]
}
```

## `$.properties.signals.items.oneOf[0].properties.sample_policy`

```json
{
  "const": "backward_hold",
  "description": "样本沿用政策。当前仅支持backward_hold，即在有效期内使用最近的有效样本。 固定值：\"backward_hold\"。",
  "default": "backward_hold"
}
```

## `$.properties.signals.items.oneOf[0].properties.same_time_policy`

```json
{
  "enum": [
    "error",
    "last_by_sequence"
  ],
  "description": "同一信号同一时刻出现多个更新时的处理方式；不忽略冲突或任意重排记录。可选值：\"error\"：同刻更新冲突时失败；\"last_by_sequence\"：按原顺序取最后一次更新。",
  "default": "error"
}
```

## `$.properties.signals.items.oneOf[0].properties.code_dtype`

```json
{
  "enum": [
    "int64",
    "uint64"
  ],
  "description": "v4 枚举的原始整数类型。enum_code 使用；CAN 可由无缩放整数 DBC 确定。"
}
```

## `$.properties.signals.items.oneOf[0].properties.choices`

```json
{
  "type": "array",
  "description": "枚举的[原编码,标签]二元数组；保留编码原生类型，不能用对象键把整数或布尔编码字符串化。 dtype=enum且省略时读取DBC枚举表；显式映射优先。缩放产生浮点枚举码时明确报错，不截断为整数。"
}
```

## `$.properties.signals.items.oneOf[0].properties.choices.items`

```json
{
  "type": "array",
  "prefixItems": [
    {
      "type": [
        "integer",
        "boolean",
        "string"
      ]
    },
    {
      "type": [
        "string",
        "boolean"
      ]
    }
  ],
  "minItems": 2,
  "maxItems": 2
}
```

## `$.properties.signals.items.oneOf[0].properties.valid_range`

```json
{
  "type": "array",
  "minItems": 2,
  "maxItems": 2,
  "description": "允许的规范数值范围，低值到高值；超界按质量政策处理，不自动裁剪到边界。"
}
```

## `$.properties.signals.items.oneOf[0].properties.valid_range.items`

```json
{
  "type": "number"
}
```

## `$.properties.signals.items.oneOf[0].properties.invalid_values`

```json
{
  "type": "array",
  "description": "明确标记为无效的原始编码列表；无效更新会覆盖前值，不当作没有更新。",
  "default": []
}
```

## `$.properties.signals.items.oneOf[0].properties.invalid_values.items`

```json
{
  "type": [
    "number",
    "string",
    "boolean",
    "null"
  ]
}
```

## `$.properties.signals.items.oneOf[0].properties.semantic_id`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "可选业务含义标识，用于说明或角色契约；相同标识本身不会自动绑定信号。 可省略或显式null；非null时必须为非空文本。"
}
```

## `$.properties.signals.items.oneOf[0].properties.semantic_contract_version`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "本信号semantic_id所指业务含义的版本，与分析配置版本独立；不表示实际输入已核验。可省略或显式null；任意非null值必须为非空文本，并同时填写本信号的semantic_id。"
}
```

## `$.properties.signals.items.oneOf[0].properties.mapping_version`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "调用方信号映射的版本标识，便于追溯明确绑定。 可省略或显式null；非null时必须为非空文本。"
}
```

## `$.properties.signals.items.oneOf[0].properties.sign_convention`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "规范信号正负方向的明确含义，例如流入为正；不同位置或方向不应仅凭名字合并。 可省略或显式null；非null时必须为非空文本。"
}
```

## `$.properties.signals.items.oneOf[0].properties.measurement_location`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "信号的测量位置声明，供业务角色契约核对。 可省略或显式null；非null时必须为非空文本。"
}
```

## `$.properties.signals.items.oneOf[0].properties.metadata`

```json
{
  "type": "object",
  "additionalProperties": true,
  "description": "附加说明对象；允许自定义JSON原生值，但不参与隐藏转换、模板执行或业务参数推断。"
}
```

## `$.properties.signals.items.oneOf[0].properties.period`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "当前信号的固定周期，正的带单位时长，例如100ms。显式周期优先于DBC报文周期；valid_for省略时取周期的3倍。",
  "examples": [
    "100ms",
    "0.1s"
  ]
}
```

## `$.properties.signals.items.oneOf[0].properties.conversion`

```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "额外单位换算。scale和offset均省略时按输入与目标单位自动推导；显式填写任一项则校验完整系数，不重复应用DBC缩放。"
}
```

## `$.properties.signals.items.oneOf[0].properties.conversion.properties.input_unit`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "读取或DBC解码后的单位。原始CAN报文省略时从DBC取得；已解析信号CSV和内存省略时沿用目标unit。显式null无效，请省略字段。"
}
```

## `$.properties.signals.items.oneOf[0].properties.conversion.properties.scale`

```json
{
  "type": "number",
  "description": "乘法系数。两系数均省略时自动推导；只有offset显式填写时本项取1。显式系数须符合单位关系。"
}
```

## `$.properties.signals.items.oneOf[0].properties.conversion.properties.offset`

```json
{
  "type": "number",
  "description": "乘法之后加上的数值，单位为目标unit。两系数均省略时自动推导；只有scale显式填写时本项取0。"
}
```

## `$.properties.signals.items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "frame_id",
    "signals"
  ],
  "additionalProperties": false
}
```

## `$.properties.signals.items.oneOf[1].allOf[0]`

```json
{
  "if": {
    "properties": {
      "is_extended": {
        "const": false,
        "description": "显式选择标准帧时，整数ID不得超过11位范围。"
      }
    },
    "required": [
      "is_extended"
    ]
  },
  "then": {
    "properties": {
      "frame_id": {
        "maximum": 2047,
        "description": "标准帧的整数报文ID上限为2047；字符串转换后的范围由计划加载器核实。"
      }
    }
  }
}
```

## `$.properties.signals.items.oneOf[1].properties.frame_id`

```json
{
  "description": "CAN报文ID；整数或字符串均可。0x前缀为十六进制，0b为二进制，无前缀为十进制；解析后须在0至536870911内，显式标准帧最多2047。"
}
```

## `$.properties.signals.items.oneOf[1].properties.frame_id.oneOf[0]`

```json
{
  "type": "integer",
  "minimum": 0,
  "maximum": 536870911
}
```

## `$.properties.signals.items.oneOf[1].properties.frame_id.oneOf[1]`

```json
{
  "type": "string",
  "pattern": "^(?:[0-9]+|0[xX][0-9a-fA-F]+|0[bB][01]+)(?![\\s\\S])",
  "minLength": 1
}
```

## `$.properties.signals.items.oneOf[1].properties.channel`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "用户配置CAN通道从1开始，1对应内部0；省略时继承来源唯一通道。"
}
```

## `$.properties.signals.items.oneOf[1].properties.is_extended`

```json
{
  "type": "boolean",
  "description": "标准／扩展帧可选约束。省略时根据DBC和实际报文识别；只有歧义时要求补充。显式null无效。"
}
```

## `$.properties.signals.items.oneOf[1].properties.is_fd`

```json
{
  "type": "boolean",
  "description": "CAN／CAN FD可选约束。省略时根据DBC和实际报文识别；只有歧义时要求补充。显式null无效。"
}
```

## `$.properties.signals.items.oneOf[1].properties.source`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "已声明来源的name。引用必须存在，不按同名字段或语义名称自动寻找来源。"
}
```

## `$.properties.signals.items.oneOf[1].properties.period`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "当前信号的固定周期，正的带单位时长，例如100ms。显式周期优先于DBC报文周期；valid_for省略时取周期的3倍。",
  "examples": [
    "100ms",
    "0.1s"
  ]
}
```

## `$.properties.signals.items.oneOf[1].properties.valid_for`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "有效样本最多沿用的实际时长。可省略，默认取当前信号周期的3倍；用户period优先，否则取DBC所属报文周期。均无法取得时需补充period或valid_for。显式填写覆盖默认值。",
  "examples": [
    "500ms",
    "2s"
  ]
}
```

## `$.properties.signals.items.oneOf[1].properties.same_time_policy`

```json
{
  "enum": [
    "error",
    "last_by_sequence"
  ],
  "description": "同一信号同一时刻出现多个更新时的处理方式；不忽略冲突或任意重排记录。可选值：\"error\"：同刻更新冲突时失败；\"last_by_sequence\"：按原顺序取最后一次更新。",
  "default": "error"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals`

```json
{
  "type": "array",
  "minItems": 1,
  "description": "同一报文内的信号声明；只填各信号名称和所需的独立覆盖参数。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items`

```json
{
  "type": "object",
  "required": [
    "name",
    "signal"
  ],
  "additionalProperties": false
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.allOf[0]`

```json
{
  "if": {
    "properties": {
      "dtype": {
        "const": "enum",
        "description": "显式enum使用文字标签；CAN可从DBC补枚举表，已解析数据需提供choices。"
      }
    },
    "required": [
      "dtype"
    ]
  },
  "then": {
    "properties": {
      "choices": {
        "minItems": 1,
        "description": "枚举的[原编码,标签]二元数组；保留编码原生类型，不能用对象键把整数或布尔编码字符串化。"
      }
    },
    "allOf": [
      {
        "if": {
          "properties": {
            "field": {
              "type": "string",
              "description": "已解析信号的列名没有DBC类型和单位元数据，需由配置明确声明。"
            }
          },
          "required": [
            "field"
          ]
        },
        "then": {
          "required": [
            "choices"
          ]
        }
      }
    ]
  }
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.allOf[1]`

```json
{
  "if": {
    "properties": {
      "field": {
        "type": "string",
        "description": "已解析信号的列名没有DBC类型和单位元数据，需由配置明确声明。"
      }
    },
    "required": [
      "field"
    ]
  },
  "then": {
    "required": [
      "dtype",
      "unit"
    ]
  }
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "当前来源或信号的简单名称，供后续声明引用；不是对原数据字段的猜测或重命名。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.dtype`

```json
{
  "enum": [
    "int64",
    "uint64",
    "float64",
    "bool",
    "enum"
  ],
  "description": "分析信号类型：int64、uint64、float64、bool或enum。CAN省略时按DBC解码值推导数值类型，不因DBC存在枚举表自动改为enum；明确手工choices为文字或布尔标签时可确定enum或bool。已解析数据仍需声明dtype。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.unit`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。 CAN省略时读取DBC单位；DBC未定义则使用unknown并标为未核实，逻辑类型用1。已解析数据仍需填写。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.valid_for`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "有效样本最多沿用的实际时长。可省略，默认取当前信号周期的3倍；用户period优先，否则取DBC所属报文周期。均无法取得时需补充period或valid_for。显式填写覆盖默认值。",
  "examples": [
    "500ms",
    "2s"
  ]
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.sample_policy`

```json
{
  "const": "backward_hold",
  "description": "样本沿用政策。当前仅支持backward_hold，即在有效期内使用最近的有效样本。 固定值：\"backward_hold\"。",
  "default": "backward_hold"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.same_time_policy`

```json
{
  "enum": [
    "error",
    "last_by_sequence"
  ],
  "description": "同一信号同一时刻出现多个更新时的处理方式；不忽略冲突或任意重排记录。可选值：\"error\"：同刻更新冲突时失败；\"last_by_sequence\"：按原顺序取最后一次更新。",
  "default": "error"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.code_dtype`

```json
{
  "enum": [
    "int64",
    "uint64"
  ],
  "description": "v4 枚举映射前的整数类型，enum_code 按需读取。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.choices`

```json
{
  "type": "array",
  "description": "枚举的[原编码,标签]二元数组；保留编码原生类型，不能用对象键把整数或布尔编码字符串化。 dtype=enum且省略时读取DBC枚举表；显式映射优先。缩放产生浮点枚举码时明确报错，不截断为整数。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.choices.items`

```json
{
  "type": "array",
  "prefixItems": [
    {
      "type": [
        "integer",
        "boolean",
        "string"
      ]
    },
    {
      "type": [
        "string",
        "boolean"
      ]
    }
  ],
  "minItems": 2,
  "maxItems": 2
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.valid_range`

```json
{
  "type": "array",
  "minItems": 2,
  "maxItems": 2,
  "description": "允许的规范数值范围，低值到高值；超界按质量政策处理，不自动裁剪到边界。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.valid_range.items`

```json
{
  "type": "number"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.invalid_values`

```json
{
  "type": "array",
  "description": "明确标记为无效的原始编码列表；无效更新会覆盖前值，不当作没有更新。",
  "default": []
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.invalid_values.items`

```json
{
  "type": [
    "number",
    "string",
    "boolean",
    "null"
  ]
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.semantic_id`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "可选业务含义标识，用于说明或角色契约；相同标识本身不会自动绑定信号。 可省略或显式null；非null时必须为非空文本。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.semantic_contract_version`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "本信号semantic_id所指业务含义的版本，与分析配置版本独立；不表示实际输入已核验。可省略或显式null；任意非null值必须为非空文本，并同时填写本信号的semantic_id。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.mapping_version`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "调用方信号映射的版本标识，便于追溯明确绑定。 可省略或显式null；非null时必须为非空文本。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.sign_convention`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "规范信号正负方向的明确含义，例如流入为正；不同位置或方向不应仅凭名字合并。 可省略或显式null；非null时必须为非空文本。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.measurement_location`

```json
{
  "type": [
    "string",
    "null"
  ],
  "minLength": 1,
  "pattern": "\\S",
  "description": "信号的测量位置声明，供业务角色契约核对。 可省略或显式null；非null时必须为非空文本。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.metadata`

```json
{
  "type": "object",
  "additionalProperties": true,
  "description": "附加说明对象；允许自定义JSON原生值，但不参与隐藏转换、模板执行或业务参数推断。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.period`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "当前信号的固定周期，正的带单位时长，例如100ms。显式周期优先于DBC报文周期；valid_for省略时取周期的3倍。",
  "examples": [
    "100ms",
    "0.1s"
  ]
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.signal`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "计算输入的已绑定信号名，或CAN定位中的原DBC信号名；两种上下文分别检查。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.conversion`

```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "额外单位换算。scale和offset均省略时按输入与目标单位自动推导；显式填写任一项则校验完整系数，不重复应用DBC缩放。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.conversion.properties.input_unit`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "读取或DBC解码后的单位。原始CAN报文省略时从DBC取得；已解析信号CSV和内存省略时沿用目标unit。显式null无效，请省略字段。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.conversion.properties.scale`

```json
{
  "type": "number",
  "description": "乘法系数。两系数均省略时自动推导；只有offset显式填写时本项取1。显式系数须符合单位关系。"
}
```

## `$.properties.signals.items.oneOf[1].properties.signals.items.properties.conversion.properties.offset`

```json
{
  "type": "number",
  "description": "乘法之后加上的数值，单位为目标unit。两系数均省略时自动推导；只有scale显式填写时本项取0。"
}
```

## `$.properties.derived`

```json
{
  "type": "object",
  "propertyNames": {
    "type": "string",
    "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
    "not": {
      "enum": [
        "abs",
        "isclose",
        "False",
        "None",
        "True",
        "and",
        "as",
        "assert",
        "async",
        "await",
        "break",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "finally",
        "for",
        "from",
        "global",
        "if",
        "import",
        "in",
        "is",
        "lambda",
        "nonlocal",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "try",
        "while",
        "with",
        "yield"
      ],
      "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
    }
  },
  "additionalProperties": {
    "type": "object",
    "properties": {
      "expr": {
        "type": "string",
        "minLength": 1,
        "pattern": "\\S",
        "description": "受限表达式，只引用明确绑定名称和已支持运算；不执行Python、属性访问或任意函数。"
      },
      "unit": {
        "type": "string",
        "minLength": 1,
        "pattern": "\\S",
        "description": "可选结果单位；省略时按表达式已支持的单位关系推导，无法确定时明确报错。"
      },
      "semantic_id": {
        "type": "string",
        "minLength": 1,
        "pattern": "\\S",
        "description": "可选业务含义标识，用于说明或角色契约；相同标识本身不会自动绑定信号。"
      },
      "semantic_contract_version": {
        "type": "string",
        "minLength": 1,
        "pattern": "\\S",
        "description": "该语义契约的版本，与分析配置版本独立；不表示实际输入已核验。"
      },
      "sign_convention": {
        "type": "string",
        "minLength": 1,
        "pattern": "\\S",
        "description": "规范信号正负方向的明确含义，例如流入为正；不同位置或方向不应仅凭名字合并。"
      },
      "measurement_location": {
        "type": "string",
        "minLength": 1,
        "pattern": "\\S",
        "description": "信号的测量位置声明，供业务角色契约核对。"
      },
      "metadata": {
        "type": "object",
        "additionalProperties": true,
        "description": "附加说明对象；允许自定义JSON原生值，但不参与隐藏转换、模板执行或业务参数推断。"
      }
    },
    "required": [
      "expr"
    ],
    "additionalProperties": false
  },
  "description": "派生信号名称到表达式声明的映射。只使用已绑定信号和受限表达式，检查单位与依赖循环。",
  "default": {}
}
```

## `$.properties.rules`

```json
{
  "type": "array",
  "description": "识别事件的规则列表。规则name与窗口、计算项和序列共享唯一名称空间。",
  "default": []
}
```

## `$.properties.rules.items.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule_type",
    "condition",
    "minimum_duration",
    "duration_comparison"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[0].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.rules.items.oneOf[0].properties.condition`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "布尔条件表达式。未知值按三值逻辑处理，不把非零数值隐式当真。"
}
```

## `$.properties.rules.items.oneOf[0].properties.selection_origin`

```json
{
  "enum": [
    "onset",
    "confirmed"
  ],
  "description": "持续条件事件的统计起点，选择首次成立时刻或持续时间得到确认的时刻。可选值：\"onset\"：从条件首次成立时刻计算；\"confirmed\"：从持续条件确认时刻计算。",
  "default": "onset"
}
```

## `$.properties.rules.items.oneOf[0].properties.rule_type`

```json
{
  "const": "condition_duration",
  "description": "事件规则类型，决定条件、时长、阈值及其他字段的含义。 固定值：\"condition_duration\"（条件连续成立达到最短时长后确认活动）。"
}
```

## `$.properties.rules.items.oneOf[0].properties.minimum_duration`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "条件连续成立的最短确认时长，必须带单位；不是样本有效期或等待上限。",
  "examples": [
    "0s",
    "500ms"
  ]
}
```

## `$.properties.rules.items.oneOf[0].properties.duration_comparison`

```json
{
  "type": "string",
  "enum": [
    ">=",
    ">"
  ],
  "description": "持续时间与minimum_duration的比较，必须明确填写：>=达到，>严格超过。60秒整仅符合>=；不更改活动起点，selection_origin仍默认onset。"
}
```

## `$.properties.rules.items.oneOf[0].properties.interval`

```json
{
  "description": "此节点采用的间隔来源；省略则继承全局default，多个驱动候选时须明确driver。"
}
```

## `$.properties.rules.items.oneOf[0].properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[0].properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"actual\"。"
}
```

## `$.properties.rules.items.oneOf[0].properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[0].properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"fixed\"。"
}
```

## `$.properties.rules.items.oneOf[0].properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "fixed计算间隔的带单位正时长，例如100ms；actual/dbc不接受此字段。"
}
```

## `$.properties.rules.items.oneOf[0].properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.rules.items.oneOf[0].properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[0].properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"dbc\"。"
}
```

## `$.properties.rules.items.oneOf[0].properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.rules.items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule_type",
    "condition"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[1].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.rules.items.oneOf[1].properties.condition`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "布尔条件表达式。未知值按三值逻辑处理，不把非零数值隐式当真。"
}
```

## `$.properties.rules.items.oneOf[1].properties.emit_initial`

```json
{
  "type": "boolean",
  "description": "第一次已知条件已经成立时是否触发。默认值按规则类型确定，下降沿不允许开启。",
  "default": false
}
```

## `$.properties.rules.items.oneOf[1].properties.rule_type`

```json
{
  "const": "rising_edge",
  "description": "事件规则类型，决定条件、时长、阈值及其他字段的含义。 固定值：\"rising_edge\"（条件由假变真时产生点事件）。"
}
```

## `$.properties.rules.items.oneOf[1].properties.interval`

```json
{
  "description": "此节点采用的间隔来源；省略则继承全局default，多个驱动候选时须明确driver。"
}
```

## `$.properties.rules.items.oneOf[1].properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[1].properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"actual\"。"
}
```

## `$.properties.rules.items.oneOf[1].properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[1].properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"fixed\"。"
}
```

## `$.properties.rules.items.oneOf[1].properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "fixed计算间隔的带单位正时长，例如100ms；actual/dbc不接受此字段。"
}
```

## `$.properties.rules.items.oneOf[1].properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.rules.items.oneOf[1].properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[1].properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"dbc\"。"
}
```

## `$.properties.rules.items.oneOf[1].properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.rules.items.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule_type",
    "condition"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[2].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.rules.items.oneOf[2].properties.condition`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "布尔条件表达式。未知值按三值逻辑处理，不把非零数值隐式当真。"
}
```

## `$.properties.rules.items.oneOf[2].properties.emit_initial`

```json
{
  "const": false,
  "description": "第一次已知条件已经成立时是否触发。默认值按规则类型确定，下降沿不允许开启。 固定值：false。",
  "default": false
}
```

## `$.properties.rules.items.oneOf[2].properties.rule_type`

```json
{
  "const": "falling_edge",
  "description": "事件规则类型，决定条件、时长、阈值及其他字段的含义。 固定值：\"falling_edge\"（条件由真变假时产生点事件）。"
}
```

## `$.properties.rules.items.oneOf[2].properties.interval`

```json
{
  "description": "此节点采用的间隔来源；省略则继承全局default，多个驱动候选时须明确driver。"
}
```

## `$.properties.rules.items.oneOf[2].properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[2].properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"actual\"。"
}
```

## `$.properties.rules.items.oneOf[2].properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[2].properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"fixed\"。"
}
```

## `$.properties.rules.items.oneOf[2].properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "fixed计算间隔的带单位正时长，例如100ms；actual/dbc不接受此字段。"
}
```

## `$.properties.rules.items.oneOf[2].properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.rules.items.oneOf[2].properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[2].properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"dbc\"。"
}
```

## `$.properties.rules.items.oneOf[2].properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.rules.items.oneOf[3]`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule_type",
    "condition",
    "window_duration"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[3].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.rules.items.oneOf[3].properties.condition`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "布尔条件表达式。未知值按三值逻辑处理，不把非零数值隐式当真。"
}
```

## `$.properties.rules.items.oneOf[3].properties.window_duration`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "start_only触发后的固定窗口长度，必须是正时长；窗口结束不因持续为真而自动重触发。"
}
```

## `$.properties.rules.items.oneOf[3].properties.emit_initial`

```json
{
  "type": "boolean",
  "description": "第一次已知条件已经成立时是否触发。默认值按规则类型确定，下降沿不允许开启。",
  "default": false
}
```

## `$.properties.rules.items.oneOf[3].properties.rule_type`

```json
{
  "const": "start_only",
  "description": "事件规则类型，决定条件、时长、阈值及其他字段的含义。 固定值：\"start_only\"（触发后生成固定窗口并抑制窗口内重复触发）。"
}
```

## `$.properties.rules.items.oneOf[3].properties.interval`

```json
{
  "description": "此节点采用的间隔来源；省略则继承全局default，多个驱动候选时须明确driver。"
}
```

## `$.properties.rules.items.oneOf[3].properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[3].properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"actual\"。"
}
```

## `$.properties.rules.items.oneOf[3].properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[3].properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"fixed\"。"
}
```

## `$.properties.rules.items.oneOf[3].properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "fixed计算间隔的带单位正时长，例如100ms；actual/dbc不接受此字段。"
}
```

## `$.properties.rules.items.oneOf[3].properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.rules.items.oneOf[3].properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[3].properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"dbc\"。"
}
```

## `$.properties.rules.items.oneOf[3].properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.rules.items.oneOf[4]`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule_type",
    "signal",
    "window",
    "direction",
    "threshold"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[4].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.rules.items.oneOf[4].properties.signal`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "window_delta检查的数值信号名或白名单数值表达式；不是DBC原名称，也不是布尔条件。"
}
```

## `$.properties.rules.items.oneOf[4].properties.window`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "变化量计算的完整回看窗口长度，必须为带单位正时长；不是窗口id。"
}
```

## `$.properties.rules.items.oneOf[4].properties.direction`

```json
{
  "enum": [
    "rise",
    "fall",
    "any"
  ],
  "description": "窗口变化量的比较方向：上升、下降或绝对变化。可选值：\"rise\"：末值减首值；\"fall\"：首值减末值；\"any\"：首末差值的绝对值。"
}
```

## `$.properties.rules.items.oneOf[4].properties.threshold`

```json
{
  "type": "number",
  "minimum": 0,
  "description": "变化量门槛，与输入信号单位一致，非负且包含等于门槛；不能猜业务阈值。"
}
```

## `$.properties.rules.items.oneOf[4].properties.monotonic`

```json
{
  "type": "boolean",
  "description": "是否要求回看窗口内保持单调，默认false；方向仍由direction决定。",
  "default": false
}
```

## `$.properties.rules.items.oneOf[4].properties.coverage_policy`

```json
{
  "const": "full",
  "description": "窗口变化量的观测覆盖政策，当前仅接受full，必须覆盖完整回看窗口。 固定值：\"full\"。",
  "default": "full"
}
```

## `$.properties.rules.items.oneOf[4].properties.emit_initial`

```json
{
  "type": "boolean",
  "description": "第一次已知条件已经成立时是否触发。默认值按规则类型确定，下降沿不允许开启。",
  "default": false
}
```

## `$.properties.rules.items.oneOf[4].properties.retrigger`

```json
{
  "enum": [
    "edge",
    "once"
  ],
  "description": "窗口变化量事件的再次触发方式，edge要求条件重新由假变真，once每个会话最多一次。可选值：\"edge\"：条件重新由假变真后可再次触发；\"once\"：每个会话最多触发一次。",
  "default": "edge"
}
```

## `$.properties.rules.items.oneOf[4].properties.rule_type`

```json
{
  "const": "window_delta",
  "description": "事件规则类型，决定条件、时长、阈值及其他字段的含义。 固定值：\"window_delta\"（检查完整回看窗口内的变化量）。"
}
```

## `$.properties.rules.items.oneOf[4].properties.interval`

```json
{
  "description": "此节点采用的间隔来源；省略则继承全局default，多个驱动候选时须明确driver。"
}
```

## `$.properties.rules.items.oneOf[4].properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[4].properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"actual\"。"
}
```

## `$.properties.rules.items.oneOf[4].properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[4].properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"fixed\"。"
}
```

## `$.properties.rules.items.oneOf[4].properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "fixed计算间隔的带单位正时长，例如100ms；actual/dbc不接受此字段。"
}
```

## `$.properties.rules.items.oneOf[4].properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.rules.items.oneOf[4].properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[4].properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"dbc\"。"
}
```

## `$.properties.rules.items.oneOf[4].properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.rules.items.oneOf[5]`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule_type",
    "condition"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[5].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.rules.items.oneOf[5].properties.condition`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "布尔条件表达式。未知值按三值逻辑处理，不把非零数值隐式当真。"
}
```

## `$.properties.rules.items.oneOf[5].properties.enter_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "进入条件连续满足多久才进入活动，带单位非负时长，省略为0s。",
  "default": "0s"
}
```

## `$.properties.rules.items.oneOf[5].properties.exit_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "退出条件连续满足多久才退出或合并片段的退出延迟；由所在规则/窗口明确含义，必须带单位。",
  "default": "0s"
}
```

## `$.properties.rules.items.oneOf[5].properties.rule_type`

```json
{
  "const": "debounce",
  "description": "事件规则类型，决定条件、时长、阈值及其他字段的含义。 固定值：\"debounce\"（条件稳定达到延迟后切换活动状态）。"
}
```

## `$.properties.rules.items.oneOf[5].properties.interval`

```json
{
  "description": "此节点采用的间隔来源；省略则继承全局default，多个驱动候选时须明确driver。"
}
```

## `$.properties.rules.items.oneOf[5].properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[5].properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"actual\"。"
}
```

## `$.properties.rules.items.oneOf[5].properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[5].properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"fixed\"。"
}
```

## `$.properties.rules.items.oneOf[5].properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "fixed计算间隔的带单位正时长，例如100ms；actual/dbc不接受此字段。"
}
```

## `$.properties.rules.items.oneOf[5].properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.rules.items.oneOf[5].properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[5].properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"dbc\"。"
}
```

## `$.properties.rules.items.oneOf[5].properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.rules.items.oneOf[6]`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule_type",
    "enter_condition",
    "exit_condition"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[6].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.rules.items.oneOf[6].properties.enter_condition`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "迟滞进入活动的布尔表达式，与退出条件分开声明。"
}
```

## `$.properties.rules.items.oneOf[6].properties.exit_condition`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "迟滞退出活动的布尔表达式，不默认等于进入条件取反。"
}
```

## `$.properties.rules.items.oneOf[6].properties.enter_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "进入条件连续满足多久才进入活动，带单位非负时长，省略为0s。",
  "default": "0s"
}
```

## `$.properties.rules.items.oneOf[6].properties.exit_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "退出条件连续满足多久才退出或合并片段的退出延迟；由所在规则/窗口明确含义，必须带单位。",
  "default": "0s"
}
```

## `$.properties.rules.items.oneOf[6].properties.rule_type`

```json
{
  "const": "hysteresis",
  "description": "事件规则类型，决定条件、时长、阈值及其他字段的含义。 固定值：\"hysteresis\"（分别声明进入和退出条件及稳定时间）。"
}
```

## `$.properties.rules.items.oneOf[6].properties.interval`

```json
{
  "description": "此节点采用的间隔来源；省略则继承全局default，多个驱动候选时须明确driver。"
}
```

## `$.properties.rules.items.oneOf[6].properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[6].properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"actual\"。"
}
```

## `$.properties.rules.items.oneOf[6].properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[6].properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"fixed\"。"
}
```

## `$.properties.rules.items.oneOf[6].properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "fixed计算间隔的带单位正时长，例如100ms；actual/dbc不接受此字段。"
}
```

## `$.properties.rules.items.oneOf[6].properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.rules.items.oneOf[6].properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[6].properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"dbc\"。"
}
```

## `$.properties.rules.items.oneOf[6].properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.rules.items.oneOf[7]`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule_type",
    "start_condition",
    "end_condition"
  ],
  "additionalProperties": false,
  "description": "开始条件启动活动，结束条件正常结束；可判断却达到时限时标timeout。"
}
```

## `$.properties.rules.items.oneOf[7].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.rules.items.oneOf[7].properties.start_condition`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "开始活动的布尔表达式；与end_condition形成开始/结束规则。"
}
```

## `$.properties.rules.items.oneOf[7].properties.end_condition`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "结束当前活动的布尔表达式；条件未知不等同于已知结束。"
}
```

## `$.properties.rules.items.oneOf[7].properties.timeout`

```json
{
  "description": "开始后允许等待的正时长上限。null或省略表示不限时；与valid_for样本有效期不同。",
  "default": null
}
```

## `$.properties.rules.items.oneOf[7].properties.timeout.anyOf[0]`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$"
}
```

## `$.properties.rules.items.oneOf[7].properties.timeout.anyOf[1]`

```json
{
  "type": "null"
}
```

## `$.properties.rules.items.oneOf[7].properties.emit_initial`

```json
{
  "type": "boolean",
  "description": "第一次已知条件已经成立时是否触发。默认值按规则类型确定，下降沿不允许开启。",
  "default": true
}
```

## `$.properties.rules.items.oneOf[7].properties.rule_type`

```json
{
  "const": "start_end",
  "description": "事件规则类型，决定条件、时长、阈值及其他字段的含义。 固定值：\"start_end\"（明确开始/结束条件，可设置等待上限）。"
}
```

## `$.properties.rules.items.oneOf[7].properties.interval`

```json
{
  "description": "此节点采用的间隔来源；省略则继承全局default，多个驱动候选时须明确driver。"
}
```

## `$.properties.rules.items.oneOf[7].properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[7].properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"actual\"。"
}
```

## `$.properties.rules.items.oneOf[7].properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[7].properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"fixed\"。"
}
```

## `$.properties.rules.items.oneOf[7].properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "fixed计算间隔的带单位正时长，例如100ms；actual/dbc不接受此字段。"
}
```

## `$.properties.rules.items.oneOf[7].properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.rules.items.oneOf[7].properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.rules.items.oneOf[7].properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"dbc\"。"
}
```

## `$.properties.rules.items.oneOf[7].properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.windows`

```json
{
  "type": "array",
  "description": "由事件生成的取数片段，指定前后扩展及片段合并方式。",
  "default": []
}
```

## `$.properties.windows.items`

```json
{
  "type": "object",
  "required": [
    "name",
    "rule"
  ],
  "additionalProperties": false
}
```

## `$.properties.windows.items.allOf[0]`

```json
{
  "if": {
    "properties": {
      "merge": {
        "const": "exit_delay",
        "description": "相邻事件生成片段的合并方式，不改变原事件本身。 固定值：\"exit_delay\"（在退出延迟内将重入合并为同一片段）。"
      }
    },
    "required": [
      "merge"
    ]
  },
  "then": {
    "required": [
      "exit_delay"
    ],
    "properties": {
      "anchor": {
        "const": "activity",
        "description": "窗口按点事件还是活动区间定位，必须与引用规则产生的事件类型一致。 固定值：\"activity\"（以活动起止区间为基础）。"
      }
    }
  },
  "else": {
    "not": {
      "required": [
        "exit_delay"
      ]
    }
  }
}
```

## `$.properties.windows.items.properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.windows.items.properties.rule`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "生成此窗口的已声明事件规则name。"
}
```

## `$.properties.windows.items.properties.anchor`

```json
{
  "enum": [
    "point",
    "activity"
  ],
  "description": "窗口按点事件还是活动区间定位，必须与引用规则产生的事件类型一致。可选值：\"point\"：以点事件为中心；\"activity\"：以活动起止区间为基础。 省略时由关联规则推导。"
}
```

## `$.properties.windows.items.properties.pre`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "事件之前扩展的非负带单位时长，省略为0s。"
}
```

## `$.properties.windows.items.properties.post`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "事件之后扩展的非负带单位时长。通常省略为0s；start_only沿用对应规则window_duration，合并规则仍检查组合约束。"
}
```

## `$.properties.windows.items.properties.merge`

```json
{
  "enum": [
    "none",
    "overlap",
    "overlap_and_adjacent",
    "exit_delay"
  ],
  "description": "相邻事件生成片段的合并方式，不改变原事件本身。可选值：\"none\"：每个片段分别保留；\"overlap\"：合并重叠片段；\"overlap_and_adjacent\"：合并重叠或相邻片段；\"exit_delay\"：在退出延迟内将重入合并为同一片段。",
  "default": "none"
}
```

## `$.properties.windows.items.properties.exit_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "退出条件连续满足多久才退出或合并片段的退出延迟；由所在规则/窗口明确含义，必须带单位。"
}
```

## `$.properties.windows.items.properties.interval`

```json
{
  "description": "此节点采用的间隔来源；省略则继承全局default，多个驱动候选时须明确driver。"
}
```

## `$.properties.windows.items.properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.windows.items.properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"actual\"。"
}
```

## `$.properties.windows.items.properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

## `$.properties.windows.items.properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"fixed\"。"
}
```

## `$.properties.windows.items.properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "fixed计算间隔的带单位正时长，例如100ms；actual/dbc不接受此字段。"
}
```

## `$.properties.windows.items.properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.windows.items.properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.windows.items.properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"dbc\"。"
}
```

## `$.properties.windows.items.properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.calculations`

```json
{
  "type": "array",
  "description": "统计、积分、时长或记录选择的计算项。每项明确操作、作用范围和输入。",
  "default": []
}
```

## `$.properties.calculations.items`

```json
{
  "type": "object",
  "required": [
    "name",
    "operation"
  ],
  "additionalProperties": false
}
```

## `$.properties.calculations.items.allOf[0]`

```json
{
  "if": {
    "required": [
      "operation"
    ],
    "properties": {
      "operation": {
        "$ref": "#/properties/calculations/items/properties/operation",
        "description": "计算操作。明确区分样本统计和时间加权统计，不接受含义不明的mean/min/max。可选值：\"select\"：选择符合条件的记录；\"sample_minimum\"：有效样本最小值；\"sample_maximum\"：有效样本最大值；\"sample_mean\"：有效样本等权均值；\"min_time\"：有效持续区间内的最小值；\"max_time\"：有效持续区间内的最大值；\"time_weighted_mean\"：按有效持续时间加权的均值；\"duration\"：条件为真的累计时长；\"integral\"：按前值保持计算积分。 版本4另支持计数：sample_count计有效样本，point_event_count计点事件，activity_count计活动，segment_count计最终片段。"
      }
    }
  },
  "then": {
    "allOf": [
      {
        "if": {
          "properties": {
            "operation": {
              "const": "duration",
              "description": "计算操作。明确区分样本统计和时间加权统计，不接受含义不明的mean/min/max。 固定值：\"duration\"（条件为真的累计时长）。"
            }
          }
        },
        "then": {
          "oneOf": [
            {
              "required": [
                "expr"
              ],
              "not": {
                "required": [
                  "condition"
                ]
              }
            },
            {
              "required": [
                "condition"
              ],
              "not": {
                "required": [
                  "expr"
                ]
              }
            }
          ]
        },
        "else": {
          "if": {
            "properties": {
              "operation": {
                "enum": [
                  "point_event_count",
                  "activity_count",
                  "segment_count"
                ],
                "description": "选择这项计算执行的具名操作。"
              }
            }
          },
          "else": {
            "required": [
              "expr"
            ]
          }
        }
      },
      {
        "if": {
          "properties": {
            "operation": {
              "const": "integral",
              "description": "计算操作。明确区分样本统计和时间加权统计，不接受含义不明的mean/min/max。 固定值：\"integral\"（按前值保持计算积分）。"
            }
          }
        },
        "else": {
          "not": {
            "required": [
              "method"
            ]
          }
        }
      },
      {
        "if": {
          "properties": {
            "operation": {
              "enum": [
                "point_event_count",
                "activity_count"
              ],
              "description": "选择这项计算执行的具名操作。"
            }
          }
        },
        "then": {
          "required": [
            "rule"
          ]
        },
        "else": {
          "properties": {
            "rule": {
              "not": {},
              "description": "在当前版本或操作下不能填写字段 rule。"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "operation": {
              "enum": [
                "segment_count"
              ],
              "description": "选择这项计算执行的具名操作。"
            }
          }
        },
        "then": {
          "required": [
            "window"
          ]
        },
        "else": {
          "properties": {
            "window": {
              "not": {},
              "description": "在当前版本或操作下不能填写字段 window。"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "operation": {
              "enum": [
                "sample_count",
                "point_event_count",
                "activity_count",
                "segment_count"
              ],
              "description": "选择这项计算执行的具名操作。"
            }
          }
        },
        "then": {
          "properties": {
            "unit": {
              "const": "1",
              "description": "希望结果采用的单位，必须与计算量兼容。"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "operation": {
              "enum": [
                "point_event_count",
                "activity_count",
                "segment_count"
              ],
              "description": "选择这项计算执行的具名操作。"
            }
          }
        },
        "then": {
          "properties": {
            "scope": {
              "const": "session",
              "description": "选择本次计算所用的会话、事件或窗口范围。"
            },
            "expr": {
              "not": {},
              "description": "在当前版本或操作下不能填写字段 expr。"
            },
            "condition": {
              "not": {},
              "description": "在当前版本或操作下不能填写字段 condition。"
            },
            "method": {
              "not": {},
              "description": "在当前版本或操作下不能填写字段 method。"
            },
            "minimum_coverage": {
              "not": {},
              "description": "在当前版本或操作下不能填写字段 minimum_coverage。"
            },
            "interval": {
              "not": {},
              "description": "在当前版本或操作下不能填写字段 interval。"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "operation": {
              "enum": [
                "sample_variance",
                "sample_stddev",
                "time_variance",
                "time_stddev"
              ],
              "description": "选择这项计算执行的具名操作。"
            }
          }
        },
        "else": {
          "properties": {
            "ddof": {
              "not": {},
              "description": "在当前版本或操作下不能填写字段 ddof。"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "operation": {
              "enum": [
                "time_variance",
                "time_stddev"
              ],
              "description": "选择这项计算执行的具名操作。"
            }
          }
        },
        "then": {
          "properties": {
            "ddof": {
              "const": 0,
              "description": "方差或标准差分母使用的自由度修正。"
            }
          }
        }
      },
      {
        "if": {
          "properties": {
            "operation": {
              "const": "sample_quantile",
              "description": "选择这项计算执行的具名操作。"
            }
          }
        },
        "then": {
          "required": [
            "q"
          ]
        },
        "else": {
          "properties": {
            "q": {
              "not": {},
              "description": "在当前版本或操作下不能填写字段 q。"
            }
          }
        }
      }
    ]
  }
}
```

## `$.properties.calculations.items.properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.calculations.items.properties.scope`

```json
{
  "description": "计算范围，省略为session；{rule: 名称}逐事件计算，{window: 名称}逐窗口计算，引用须已声明。"
}
```

## `$.properties.calculations.items.properties.scope.oneOf[0]`

```json
{
  "const": "session",
  "description": "分析或导出整个会话的可用范围。"
}
```

## `$.properties.calculations.items.properties.scope.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "rule"
  ],
  "additionalProperties": false
}
```

## `$.properties.calculations.items.properties.scope.oneOf[1].properties.rule`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "所引用的规则或窗口名称，必须在同一配置中已经声明。"
}
```

## `$.properties.calculations.items.properties.scope.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "window"
  ],
  "additionalProperties": false
}
```

## `$.properties.calculations.items.properties.scope.oneOf[2].properties.window`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "所引用的规则或窗口名称，必须在同一配置中已经声明。"
}
```

## `$.properties.calculations.items.properties.operation`

```json
{
  "enum": [
    "select",
    "sample_minimum",
    "sample_maximum",
    "sample_mean",
    "min_time",
    "max_time",
    "time_weighted_mean",
    "duration",
    "integral",
    "sample_count",
    "point_event_count",
    "activity_count",
    "segment_count",
    "sample_variance",
    "sample_stddev",
    "time_variance",
    "time_stddev",
    "sample_rms",
    "time_rms",
    "sample_quantile",
    "sample_median"
  ],
  "description": "计算操作。明确区分样本统计和时间加权统计，不接受含义不明的mean/min/max。可选值：\"select\"：选择符合条件的记录；\"sample_minimum\"：有效样本最小值；\"sample_maximum\"：有效样本最大值；\"sample_mean\"：有效样本等权均值；\"min_time\"：有效持续区间内的最小值；\"max_time\"：有效持续区间内的最大值；\"time_weighted_mean\"：按有效持续时间加权的均值；\"duration\"：条件为真的累计时长；\"integral\"：按前值保持计算积分。 版本4另支持计数：sample_count计有效样本，point_event_count计点事件，activity_count计活动，segment_count计最终片段。"
}
```

## `$.properties.calculations.items.properties.condition`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "布尔条件表达式。未知值按三值逻辑处理，不把非零数值隐式当真。"
}
```

## `$.properties.calculations.items.properties.unit`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "\\S",
  "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。"
}
```

## `$.properties.calculations.items.properties.method`

```json
{
  "const": "zoh",
  "description": "积分方法。当前只支持zoh，按前值保持的有效时间累计，不自动线性插值。 固定值：\"zoh\"。"
}
```

## `$.properties.calculations.items.properties.partial_policy`

```json
{
  "enum": [
    "report",
    "strict"
  ],
  "description": "有效覆盖不足时的处理政策；计算项省略则继承execution，预设按自身参数契约检查。可选值：\"report\"：报告可得的部分结果及覆盖信息；\"strict\"：按严格完整性要求处理部分结果。"
}
```

## `$.properties.calculations.items.properties.minimum_coverage`

```json
{
  "type": "number",
  "minimum": 0,
  "maximum": 1,
  "description": "需要的最小有效覆盖比例，范围0到1；不通过补零或延长有效期达到门槛。",
  "default": 0
}
```

## `$.properties.calculations.items.properties.expr`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "统计输入的信号名称或白名单表达式；编译时检查依赖、类型与单位。"
}
```

## `$.properties.calculations.items.properties.interval`

```json
{
  "description": "此节点采用的间隔来源；省略则继承全局default，多个驱动候选时须明确driver。"
}
```

## `$.properties.calculations.items.properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.calculations.items.properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"actual\"。"
}
```

## `$.properties.calculations.items.properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

## `$.properties.calculations.items.properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"fixed\"。"
}
```

## `$.properties.calculations.items.properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "fixed计算间隔的带单位正时长，例如100ms；actual/dbc不接受此字段。"
}
```

## `$.properties.calculations.items.properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.calculations.items.properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.calculations.items.properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"dbc\"。"
}
```

## `$.properties.calculations.items.properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.calculations.items.properties.rule`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "要计数的点事件或活动规则名称，仅用于对象计数。"
}
```

## `$.properties.calculations.items.properties.window`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "要计数的最终片段来自哪个窗口，仅用于segment_count。"
}
```

## `$.properties.calculations.items.properties.ddof`

```json
{
  "type": "integer",
  "enum": [
    0,
    1
  ],
  "description": "样本方差和标准差的自由度修正：0表示总体，1表示按N−1计算；时间加权只允许0。"
}
```

## `$.properties.calculations.items.properties.q`

```json
{
  "type": "number",
  "minimum": 0,
  "maximum": 1,
  "description": "精确分位数的位置，0表示最小值、1最大值、0.95表示P95。仅sample_quantile填写。"
}
```

## `$.properties.presets`

```json
{
  "type": "array",
  "description": "预设把明确绑定的角色和参数展开为普通规则、窗口与计算；不按信号名称猜角色或阈值。",
  "default": []
}
```

## `$.properties.presets.items.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "name",
    "preset_type",
    "parameters"
  ],
  "additionalProperties": false
}
```

## `$.properties.presets.items.oneOf[0].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.presets.items.oneOf[0].properties.version`

```json
{
  "const": "1",
  "description": "预设契约版本，可省略，默认字符串1；与分析文件的整数config_version=4分别控制不同对象。"
}
```

## `$.properties.presets.items.oneOf[0].properties.role_bindings`

```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "预设角色到已绑定信号的显式映射；角色名称不代表原数据字段名。"
}
```

## `$.properties.presets.items.oneOf[0].properties.role_bindings.properties.mode`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "业务模式角色的绑定信号名，或计算间隔/导出周期的选择方式；按所在对象解释。"
}
```

## `$.properties.presets.items.oneOf[0].properties.role_bindings.properties.current`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "充电预设中电流角色绑定的信号名，必须明确单位、方向和测量位置。"
}
```

## `$.properties.presets.items.oneOf[0].properties.role_bindings.properties.voltage`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "充电预设中电压角色绑定的信号名，不能仅因名字含voltage就自动选择。"
}
```

## `$.properties.presets.items.oneOf[0].properties.parameters`

```json
{
  "type": "object",
  "required": [
    "mode_value",
    "current_min",
    "minimum_duration"
  ],
  "additionalProperties": false,
  "description": "预设所需的业务参数，或逐消息表达式的有单位数值参数；不使用未声明车型默认值。"
}
```

## `$.properties.presets.items.oneOf[0].properties.parameters.properties.mode_value`

```json
{
  "type": "integer",
  "minimum": -9223372036854775808,
  "maximum": 18446744073709551615,
  "description": "表示目标工作模式的明确整数编码，与角色信号的choices/类型相符。"
}
```

## `$.properties.presets.items.oneOf[0].properties.parameters.properties.current_min`

```json
{
  "type": "number",
  "description": "明确电流门槛，单位A；不采用车型或设备的猜测默认值。"
}
```

## `$.properties.presets.items.oneOf[0].properties.parameters.properties.compute_energy`

```json
{
  "type": "boolean",
  "default": false,
  "description": "是否生成充电能量计算，默认false；开启时需要相应角色及单位满足契约。"
}
```

## `$.properties.presets.items.oneOf[0].properties.parameters.properties.compute_charge`

```json
{
  "type": "boolean",
  "default": false,
  "description": "是否生成电量计算，默认false；开启后沿明确电流方向和有效覆盖处理。"
}
```

## `$.properties.presets.items.oneOf[0].properties.parameters.properties.minimum_coverage`

```json
{
  "type": "number",
  "minimum": 0,
  "maximum": 1,
  "default": 0,
  "description": "需要的最小有效覆盖比例，范围0到1；不通过补零或延长有效期达到门槛。"
}
```

## `$.properties.presets.items.oneOf[0].properties.parameters.properties.partial_policy`

```json
{
  "enum": [
    "report",
    "strict"
  ],
  "description": "有效覆盖不足时的处理政策；计算项省略则继承execution，预设按自身参数契约检查。可选值：\"report\"：报告可得的部分结果及覆盖信息；\"strict\"：按严格完整性要求处理部分结果。"
}
```

## `$.properties.presets.items.oneOf[0].properties.parameters.properties.minimum_duration`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "条件连续成立的最短确认时长，必须带单位；不是样本有效期或等待上限。"
}
```

## `$.properties.presets.items.oneOf[0].properties.preset_type`

```json
{
  "const": "charge_session",
  "description": "预设场景类型，先检查角色契约，再生成可检查的普通节点。 固定值：\"charge_session\"（充电活动及可选能量/电量计算）。"
}
```

## `$.properties.presets.items.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "name",
    "preset_type",
    "parameters"
  ],
  "additionalProperties": false
}
```

## `$.properties.presets.items.oneOf[1].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.presets.items.oneOf[1].properties.version`

```json
{
  "const": "1",
  "description": "预设契约版本，可省略，默认字符串1；与分析文件的整数config_version=4分别控制不同对象。"
}
```

## `$.properties.presets.items.oneOf[1].properties.role_bindings`

```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "预设角色到已绑定信号的显式映射；角色名称不代表原数据字段名。"
}
```

## `$.properties.presets.items.oneOf[1].properties.role_bindings.properties.alarm`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "故障上下文预设中报警角色绑定的布尔信号名。"
}
```

## `$.properties.presets.items.oneOf[1].properties.parameters`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "预设所需的业务参数，或逐消息表达式的有单位数值参数；不使用未声明车型默认值。"
}
```

## `$.properties.presets.items.oneOf[1].properties.parameters.properties.pre`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "在事件之前扩展的非负时长，必须带单位。"
}
```

## `$.properties.presets.items.oneOf[1].properties.parameters.properties.post`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "在事件之后扩展的非负时长，必须带单位；特定合并/固定窗口规则有额外限制。"
}
```

## `$.properties.presets.items.oneOf[1].properties.parameters.properties.emit_initial`

```json
{
  "type": "boolean",
  "default": false,
  "description": "第一次已知条件已经成立时是否触发。默认值按规则类型确定，下降沿不允许开启。"
}
```

## `$.properties.presets.items.oneOf[1].properties.preset_type`

```json
{
  "const": "fault_context",
  "description": "预设场景类型，先检查角色契约，再生成可检查的普通节点。 固定值：\"fault_context\"（报警前后上下文片段）。"
}
```

## `$.properties.presets.items.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "name",
    "preset_type",
    "parameters"
  ],
  "additionalProperties": false
}
```

## `$.properties.presets.items.oneOf[2].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.presets.items.oneOf[2].properties.version`

```json
{
  "const": "1",
  "description": "预设契约版本，可省略，默认字符串1；与分析文件的整数config_version=4分别控制不同对象。"
}
```

## `$.properties.presets.items.oneOf[2].properties.role_bindings`

```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "预设角色到已绑定信号的显式映射；角色名称不代表原数据字段名。"
}
```

## `$.properties.presets.items.oneOf[2].properties.role_bindings.properties.request`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "请求响应预设中请求角色绑定的信号名。"
}
```

## `$.properties.presets.items.oneOf[2].properties.role_bindings.properties.response`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "绑定到响应角色的已声明信号名；这是预设的信号绑定，不是sequences中的规则引用。"
}
```

## `$.properties.presets.items.oneOf[2].properties.parameters`

```json
{
  "type": "object",
  "required": [
    "max_delay"
  ],
  "additionalProperties": false,
  "description": "预设所需的业务参数，或逐消息表达式的有单位数值参数；不使用未声明车型默认值。"
}
```

## `$.properties.presets.items.oneOf[2].properties.parameters.properties.min_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "允许的最小响应延迟，非负带单位时长，包含端点。"
}
```

## `$.properties.presets.items.oneOf[2].properties.parameters.properties.max_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "允许的最大响应延迟，不得小于min_delay，包含端点；到期未响应会得到明确配对状态。"
}
```

## `$.properties.presets.items.oneOf[2].properties.parameters.properties.emit_initial`

```json
{
  "type": "boolean",
  "default": false,
  "description": "第一次已知条件已经成立时是否触发。默认值按规则类型确定，下降沿不允许开启。"
}
```

## `$.properties.presets.items.oneOf[2].properties.parameters.properties.max_pending`

```json
{
  "type": "integer",
  "minimum": 1,
  "default": 65536,
  "description": "同时等待响应的请求数上限，正整数，默认65536；不是输入文件总行数。"
}
```

## `$.properties.presets.items.oneOf[2].properties.preset_type`

```json
{
  "const": "command_response",
  "description": "预设场景类型，先检查角色契约，再生成可检查的普通节点。 固定值：\"command_response\"（请求与响应延迟配对）。"
}
```

## `$.properties.presets.items.oneOf[3]`

```json
{
  "type": "object",
  "required": [
    "name",
    "preset_type",
    "role_bindings",
    "parameters"
  ],
  "additionalProperties": false
}
```

## `$.properties.presets.items.oneOf[3].properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.presets.items.oneOf[3].properties.version`

```json
{
  "const": "1",
  "description": "预设契约版本，可省略，默认字符串1；与分析文件的整数config_version=4分别控制不同对象。"
}
```

## `$.properties.presets.items.oneOf[3].properties.role_bindings`

```json
{
  "type": "object",
  "required": [
    "signal"
  ],
  "additionalProperties": false,
  "description": "预设角色到已绑定信号的显式映射；角色名称不代表原数据字段名。"
}
```

## `$.properties.presets.items.oneOf[3].properties.role_bindings.properties.signal`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "阈值预设的signal角色使用的分析信号name；必须满足该角色的数值与单位要求。"
}
```

## `$.properties.presets.items.oneOf[3].properties.parameters`

```json
{
  "type": "object",
  "required": [
    "enter_threshold",
    "exit_threshold"
  ],
  "additionalProperties": false,
  "description": "预设所需的业务参数，或逐消息表达式的有单位数值参数；不使用未声明车型默认值。"
}
```

## `$.properties.presets.items.oneOf[3].properties.parameters.properties.unit`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "阈值单位，可省略并使用signal角色所绑定信号的单位；显式填写时必须与该信号一致，不触发额外换算。"
}
```

## `$.properties.presets.items.oneOf[3].properties.parameters.properties.enter_threshold`

```json
{
  "type": "number",
  "description": "阈值活动的进入门槛，单位与角色信号一致；与退出门槛的先后关系由方向语义检查。"
}
```

## `$.properties.presets.items.oneOf[3].properties.parameters.properties.exit_threshold`

```json
{
  "type": "number",
  "description": "阈值活动的退出门槛，不能为消除抖动而擅自猜测数值。"
}
```

## `$.properties.presets.items.oneOf[3].properties.parameters.properties.enter_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "进入条件连续满足多久才进入活动，带单位非负时长，省略为0s。"
}
```

## `$.properties.presets.items.oneOf[3].properties.parameters.properties.exit_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "退出条件连续满足多久才退出或合并片段的退出延迟；由所在规则/窗口明确含义，必须带单位。"
}
```

## `$.properties.presets.items.oneOf[3].properties.preset_type`

```json
{
  "const": "threshold_excursion",
  "description": "预设场景类型，先检查角色契约，再生成可检查的普通节点。 固定值：\"threshold_excursion\"（越限进入和恢复退出的阈值活动）。"
}
```

## `$.properties.message_calculations`

```json
{
  "type": "array",
  "description": "针对指定CAN消息的逐消息累计。每次实际消息独立求值，不施普通信号保持、不额外乘时间差。",
  "default": []
}
```

## `$.properties.message_calculations.items`

```json
{
  "type": "object",
  "required": [
    "name",
    "update_message",
    "expr",
    "unit"
  ],
  "additionalProperties": false
}
```

## `$.properties.message_calculations.items.properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.message_calculations.items.properties.source`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "逐消息累计使用的原始CAN来源name；只有一个适用来源时可省略，多候选时必须明确选择。"
}
```

## `$.properties.message_calculations.items.properties.profile`

```json
{
  "enum": [
    "sclicer-functions-v1",
    "can-text-v1"
  ],
  "description": "消息读取/解码实现标识，可省略并由来源确定：既有BLF路径使用sclicer-functions-v1，ASC、原始CAN CSV及混合来源使用can-text-v1。显式值必须与实际来源一致。"
}
```

## `$.properties.message_calculations.items.properties.operation`

```json
{
  "const": "legacy_sum",
  "description": "逐消息计算的累计方法，可省略，当前默认且仅支持legacy_sum；每条符合条件的消息独立贡献一次。"
}
```

## `$.properties.message_calculations.items.properties.message_policy`

```json
{
  "const": "current_message-v1",
  "description": "可省略，默认current_message-v1；每次只取当前目标消息的解码值，不沿用上条消息缓存。"
}
```

## `$.properties.message_calculations.items.properties.expr`

```json
{
  "type": "string",
  "pattern": "\\S",
  "description": "受限表达式，只引用明确绑定名称和已支持运算；不执行Python、属性访问或任意函数。"
}
```

## `$.properties.message_calculations.items.properties.unit`

```json
{
  "type": "string",
  "pattern": "\\S",
  "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。"
}
```

## `$.properties.message_calculations.items.properties.update_message`

```json
{
  "type": "object",
  "required": [
    "frame_id"
  ],
  "additionalProperties": false,
  "description": "触发求值的CAN报文定位；frame_id必填，channel省略采用来源通道，标准/扩展及CAN/FD限制可省略并按实际输入识别。"
}
```

## `$.properties.message_calculations.items.properties.update_message.allOf[0]`

```json
{
  "if": {
    "properties": {
      "is_extended": {
        "const": false,
        "description": "是否扩展帧，必须是布尔值；标准帧ID与扩展帧ID有不同范围。 固定值：false。"
      }
    },
    "required": [
      "is_extended"
    ]
  },
  "then": {
    "properties": {
      "frame_id": {
        "maximum": 2047,
        "description": "CAN报文ID，非负整数；范围由标准帧/扩展帧标志进一步约束。"
      }
    }
  }
}
```

## `$.properties.message_calculations.items.properties.update_message.properties.channel`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "用户配置CAN通道从1开始，1对应内部0；省略时继承来源唯一通道。"
}
```

## `$.properties.message_calculations.items.properties.update_message.properties.frame_id`

```json
{
  "description": "CAN报文ID；整数或字符串均可。0x前缀为十六进制，0b为二进制，无前缀为十进制；解析后须在0至536870911内，显式标准帧最多2047。"
}
```

## `$.properties.message_calculations.items.properties.update_message.properties.frame_id.oneOf[0]`

```json
{
  "type": "integer",
  "minimum": 0,
  "maximum": 536870911
}
```

## `$.properties.message_calculations.items.properties.update_message.properties.frame_id.oneOf[1]`

```json
{
  "type": "string",
  "pattern": "^(?:[0-9]+|0[xX][0-9a-fA-F]+|0[bB][01]+)(?![\\s\\S])",
  "minLength": 1
}
```

## `$.properties.message_calculations.items.properties.update_message.properties.is_extended`

```json
{
  "type": "boolean",
  "description": "标准／扩展帧可选约束。省略时根据DBC和实际报文识别；只有歧义时要求补充。显式null无效。"
}
```

## `$.properties.message_calculations.items.properties.update_message.properties.is_fd`

```json
{
  "type": "boolean",
  "description": "CAN／CAN FD可选约束。省略时根据DBC和实际报文识别；只有歧义时要求补充。显式null无效。"
}
```

## `$.properties.message_calculations.items.properties.split_by_sign`

```json
{
  "type": "object",
  "description": "按当前原解码字段的正负选择累计桶，不施额外归一化，也不沿用其他消息的旧值。",
  "required": [
    "signal",
    "bucket"
  ],
  "additionalProperties": false
}
```

## `$.properties.message_calculations.items.properties.split_by_sign.properties.signal`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "用于区分正负方向的分析信号name，须来自同一目标报文；允许独立于贡献expr。"
}
```

## `$.properties.message_calculations.items.properties.split_by_sign.properties.bucket`

```json
{
  "enum": [
    "positive",
    "negative"
  ],
  "description": "正值桶或负值桶的选择；方向判断依据当前指定原解码字段。可选值：\"positive\"：正向累计桶；\"negative\"：负向累计桶。"
}
```

## `$.properties.message_calculations.items.properties.split_by_sign.properties.value_policy`

```json
{
  "const": "raw_decoded-v1",
  "description": "分组使用的值，可省略，默认raw_decoded-v1；使用本条消息的原解码方向值，不额外换算、不沿用旧值。"
}
```

## `$.properties.message_calculations.items.properties.parameters`

```json
{
  "type": "object",
  "propertyNames": {
    "type": "string",
    "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
    "not": {
      "enum": [
        "abs",
        "isclose",
        "False",
        "None",
        "True",
        "and",
        "as",
        "assert",
        "async",
        "await",
        "break",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "finally",
        "for",
        "from",
        "global",
        "if",
        "import",
        "in",
        "is",
        "lambda",
        "nonlocal",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "try",
        "while",
        "with",
        "yield"
      ],
      "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
    }
  },
  "additionalProperties": {
    "type": "object",
    "required": [
      "value",
      "unit"
    ],
    "additionalProperties": false,
    "properties": {
      "value": {
        "type": "number",
        "description": "带单位的间隔文本，或有独立unit声明的表达式数值参数；按所在对象检查类型。"
      },
      "unit": {
        "type": "string",
        "pattern": "\\S",
        "description": "数值所用单位。参与表达式和转换时核对单位；不能从字段名或文件名猜测。"
      }
    }
  },
  "description": "预设所需的业务参数，或逐消息表达式的有单位数值参数；不使用未声明车型默认值。"
}
```

## `$.properties.execution`

```json
{
  "type": "object",
  "required": [],
  "additionalProperties": false,
  "description": "执行后端及分析层资源限制。预算是声明，静态检查不测量实际内存峰值。",
  "default": {}
}
```

## `$.properties.execution.properties.backend`

```json
{
  "enum": [
    "numpy",
    "reference",
    "auto"
  ],
  "description": "数值计算实现选择。auto按已验证的整个计划类别选择reference或numpy，不预读或试跑；numpy采用NumPy数值实现；reference采用独立参考实现。显式选择保持，不因运行错误切换后端。",
  "default": "auto"
}
```

## `$.properties.execution.properties.batch_rows`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "每批读取的记录/样本上限，正整数，默认65536；不等于独立任务并行数。",
  "default": 65536
}
```

## `$.properties.execution.properties.memory_budget_bytes`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "新分析层内存预算，正整数字节数，默认268435456；不是整个Python进程或旧读取器的RSS上限。",
  "default": 268435456
}
```

## `$.properties.execution.properties.result_buffer_rows`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "写出结果前的缓冲行数上限，正整数，默认4096。",
  "default": 4096
}
```

## `$.properties.execution.properties.partial_policy`

```json
{
  "enum": [
    "report",
    "strict"
  ],
  "description": "有效覆盖不足时的处理政策；计算项省略则继承execution，预设按自身参数契约检查。可选值：\"report\"：报告可得的部分结果及覆盖信息；\"strict\"：按严格完整性要求处理部分结果。",
  "default": "report"
}
```

## `$.properties.execution.properties.on_budget_exceeded`

```json
{
  "const": "error",
  "description": "超过预算的处理方式，当前只接受error，明确失败而不丢数据或增加旧输入扫描。 固定值：\"error\"。",
  "default": "error"
}
```

## `$.properties.execution.properties.spool_quota_bytes`

```json
{
  "description": "暂存磁盘配额，正整数字节数；null或省略表示未设置配额。",
  "default": null
}
```

## `$.properties.execution.properties.spool_quota_bytes.anyOf[0]`

```json
{
  "type": "null"
}
```

## `$.properties.execution.properties.spool_quota_bytes.anyOf[1]`

```json
{
  "type": "integer",
  "minimum": 1
}
```

## `$.properties.execution.properties.process_count`

```json
{
  "type": "integer",
  "minimum": 1,
  "default": 1,
  "description": "控制本次分析最多使用多少个读取和DBC解码工作进程，不包含主分析进程。填写大于等于1的整数；默认1保留串行读取。API或CLI显式参数优先于配置。多个文件仍属于同一个连续会话。"
}
```

## `$.properties.outputs`

```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "结果表及可选信号/CAN导出。正式结果目录可复用，每次使用独立时间文件名，并由本次完成清单定位。",
  "default": {}
}
```

## `$.properties.outputs.properties.contributions`

```json
{
  "enum": [
    "none",
    "full"
  ],
  "description": "是否保存逐消息贡献明细。none默认只保留汇总，full显式逐条保存。可选值：\"none\"：不保存逐条贡献明细；\"full\"：明确保存逐条贡献。",
  "default": "none"
}
```

## `$.properties.outputs.properties.tables`

```json
{
  "enum": [
    "readable_csv",
    "csv",
    "jsonl"
  ],
  "description": "结果表格式；省略时使用readable_csv，中文列名、精确秒、同区间指标合并。csv保留程序交换用平坦表和整数纳秒；jsonl保留逐行JSON。只生成所选的一套表，不决定配置文件格式。",
  "default": "readable_csv"
}
```

## `$.properties.outputs.properties.manifest`

```json
{
  "const": "json",
  "description": "运行清单文件格式，当前固定json。 固定值：\"json\"。",
  "default": "json"
}
```

## `$.properties.outputs.properties.signal_csv`

```json
{
  "description": "可选的信号CSV导出。省略或null表示关闭；开启时必须明确选择信号及范围。",
  "default": null
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[0]`

```json
{
  "type": "null"
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "signals"
  ],
  "additionalProperties": false
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.signals`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "uniqueItems": true,
  "description": "显式选择要导出的原信号别名列表；必须已在分析signals中声明，不默认导出全部信号。"
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.signals.items`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  }
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.scope`

```json
{
  "description": "明确选择整个会话、某条规则的事件范围或某个窗口的范围。"
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.scope.oneOf[0]`

```json
{
  "const": "session",
  "description": "分析或导出整个会话的可用范围。"
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.scope.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "window"
  ],
  "additionalProperties": false
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.scope.oneOf[1].properties.window`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "所引用的规则或窗口名称，必须在同一配置中已经声明。"
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling`

```json
{
  "description": "本次导出的独立重采样设置。省略或null保留原始采样；不能借导出网格改变计算间隔。"
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[0]`

```json
{
  "type": "null"
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "continuous",
    "period",
    "max_gap"
  ],
  "additionalProperties": false
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.continuous`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "uniqueItems": true,
  "description": "明确允许线性重采样的数值信号子集。状态、计数或枚举不能仅因数值类型就被当成连续量。"
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.continuous.items`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  }
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.max_gap`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "允许插值或重建的最大实际样本间隔，必须带单位且为正；不是固定时间偏移。"
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.period`

```json
{
  "description": "导出网格周期。固定周期使用正时长文本，DBC周期使用mode: dbc对象；不从文件名猜周期。"
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.period.oneOf[0]`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "固定时间偏移，只接受数值与s/ms/us/ns单位，不接受日期。"
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.period.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.period.oneOf[1].properties.mode`

```json
{
  "const": "dbc",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"dbc\"。"
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.period.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.outputs.properties.signal_csv.oneOf[1].properties.resampling.oneOf[1].properties.start`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "重采样时间网格的起点，省略为0ns；不改变分析范围或原始报文时间。"
}
```

## `$.properties.outputs.properties.can_frames`

```json
{
  "description": "可选的CAN原帧/重建帧导出。省略或null表示关闭，开启不会替代分析结果表。",
  "default": null
}
```

## `$.properties.outputs.properties.can_frames.oneOf[0]`

```json
{
  "type": "null"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "format"
  ],
  "additionalProperties": false
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].allOf[0]`

```json
{
  "if": {
    "required": [
      "capture_date"
    ]
  },
  "then": {
    "required": [
      "timezone"
    ]
  }
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].allOf[1]`

```json
{
  "if": {
    "required": [
      "timezone"
    ]
  },
  "then": {
    "required": [
      "capture_date"
    ]
  }
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].allOf[2]`

```json
{
  "if": {
    "properties": {
      "source_time_reference": {
        "const": "epoch",
        "description": "导出时间以相对起点还是Unix纪元表示。原始时间解释必须明确。 固定值：\"epoch\"（Unix纪元绝对时间）。"
      }
    },
    "required": [
      "source_time_reference"
    ]
  },
  "then": {
    "not": {
      "anyOf": [
        {
          "required": [
            "capture_date"
          ]
        },
        {
          "required": [
            "timezone"
          ]
        }
      ]
    }
  }
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.source`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "已声明来源的name。引用必须存在，不按同名字段或语义名称自动寻找来源。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.format`

```json
{
  "enum": [
    "asc",
    "blf"
  ],
  "description": "CAN输出格式，asc或blf；与结果表csv/jsonl选项分开。可选值：\"asc\"：ASC文本帧文件；\"blf\"：BLF二进制帧文件。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.scope`

```json
{
  "description": "明确选择整个会话、某条规则的事件范围或某个窗口的范围。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.scope.oneOf[0]`

```json
{
  "const": "session",
  "description": "分析或导出整个会话的可用范围。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.scope.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "window"
  ],
  "additionalProperties": false
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.scope.oneOf[1].properties.window`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "所引用的规则或窗口名称，必须在同一配置中已经声明。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.scope.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "windows"
  ],
  "additionalProperties": false
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.scope.oneOf[2].properties.windows`

```json
{
  "const": "all",
  "description": "使用所有已配置窗口生成的范围，不把all当作某个窗口名。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.source_time_reference`

```json
{
  "enum": [
    "relative",
    "epoch"
  ],
  "description": "导出时间以相对起点还是Unix纪元表示。原始时间解释必须明确。可选值：\"relative\"：相对起点时间；\"epoch\"：Unix纪元绝对时间。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.capture_date`

```json
{
  "type": "string",
  "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
  "description": "显式捕获日期，用于需要日期头的导出；不能把运行日期冒充采集日期。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.output_offset`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "导出时间轴的显式固定偏移，带s/ms/us/ns单位，不改变分析时钟。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling`

```json
{
  "description": "本次导出的独立重采样设置。省略或null保留原始采样；不能借导出网格改变计算间隔。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[0]`

```json
{
  "type": "null"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "period",
    "max_gap",
    "messages"
  ],
  "additionalProperties": false
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.max_gap`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "允许插值或重建的最大实际样本间隔，必须带单位且为正；不是固定时间偏移。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages`

```json
{
  "type": "array",
  "minItems": 0,
  "maxItems": 4096,
  "description": "CAN重建规则列表，按精确报文定位声明连续字段和受保护字段。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items`

```json
{
  "type": "object",
  "required": [
    "frame_id",
    "continuous"
  ],
  "additionalProperties": false
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.allOf[0]`

```json
{
  "if": {
    "properties": {
      "is_extended": {
        "const": false,
        "description": "显式选择标准帧时，整数ID不得超过11位范围。"
      }
    },
    "required": [
      "is_extended"
    ]
  },
  "then": {
    "properties": {
      "frame_id": {
        "maximum": 2047,
        "description": "标准帧的整数报文ID上限为2047；字符串转换后的范围由计划加载器核实。"
      }
    }
  }
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.channel`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "用户配置CAN通道从1开始，1对应内部0；省略时继承来源唯一通道。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.frame_id`

```json
{
  "description": "CAN报文ID；整数或字符串均可。0x前缀为十六进制，0b为二进制，无前缀为十进制；解析后须在0至536870911内，显式标准帧最多2047。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.frame_id.oneOf[0]`

```json
{
  "type": "integer",
  "minimum": 0,
  "maximum": 536870911
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.frame_id.oneOf[1]`

```json
{
  "type": "string",
  "pattern": "^(?:[0-9]+|0[xX][0-9a-fA-F]+|0[bB][01]+)(?![\\s\\S])",
  "minLength": 1
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.is_extended`

```json
{
  "type": "boolean",
  "description": "标准／扩展帧可选约束。省略时根据DBC和实际报文识别；只有歧义时要求补充。显式null无效。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.is_fd`

```json
{
  "type": "boolean",
  "description": "CAN／CAN FD可选约束。省略时根据DBC和实际报文识别；只有歧义时要求补充。显式null无效。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.continuous`

```json
{
  "type": "array",
  "minItems": 1,
  "maxItems": 4096,
  "uniqueItems": true,
  "description": "明确允许线性重采样的数值信号子集。状态、计数或枚举不能仅因数值类型就被当成连续量。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.continuous.items`

```json
{
  "type": "string",
  "minLength": 1
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.protected`

```json
{
  "type": "array",
  "minItems": 0,
  "maxItems": 4096,
  "uniqueItems": true,
  "description": "重建时必须保留原值的DBC信号列表，例如计数器或校验字段；不自动重算未知算法。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.protected.items`

```json
{
  "type": "string",
  "minLength": 1
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.messages.items.properties.same_time_policy`

```json
{
  "enum": [
    "error",
    "last_by_sequence"
  ],
  "description": "同一信号同一时刻出现多个更新时的处理方式；不忽略冲突或任意重排记录。可选值：\"error\"：同刻更新冲突时失败；\"last_by_sequence\"：按原顺序取最后一次更新。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.unknown_policy`

```json
{
  "enum": [
    "passthrough",
    "nearest"
  ],
  "description": "没有匹配重建规则的报文如何输出：按原时间透传，或按明确距离选择最近原帧。可选值：\"passthrough\"：不匹配重建规则的帧按原时刻透传；\"nearest\"：按明确时间距离选最近原帧。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.max_distance`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "选择最近原帧时允许的最大时间距离，必须为非负时长；0s仅接受恰好同刻的原帧。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.period`

```json
{
  "description": "导出网格周期。固定周期使用正时长文本，DBC周期使用mode: dbc对象；不从文件名猜周期。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.period.oneOf[0]`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "固定时间偏移，只接受数值与s/ms/us/ns单位，不接受日期。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.period.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.period.oneOf[1].properties.mode`

```json
{
  "const": "dbc",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"dbc\"。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.resampling.oneOf[1].properties.start`

```json
{
  "type": "string",
  "pattern": "^\\s*[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "重采样时间网格的起点，省略为0ns；不改变分析范围或原始报文时间。"
}
```

## `$.properties.outputs.properties.can_frames.oneOf[1].properties.timezone`

```json
{
  "type": [
    "string",
    "null"
  ],
  "description": "采集地点的固定时区，例如+08:00或UTC；相对时间导出BLF时与capture_date同时填写。"
}
```

## `$.properties.metadata`

```json
{
  "type": "object",
  "additionalProperties": true,
  "description": "附加说明对象；允许自定义JSON原生值，但不参与隐藏转换、模板执行或业务参数推断。",
  "default": {}
}
```

## `$.properties.sequences`

```json
{
  "type": "array",
  "description": "将请求点事件与响应点事件按FIFO配对，指定允许延迟和最多等待的请求数。",
  "default": []
}
```

## `$.properties.sequences.items`

```json
{
  "type": "object",
  "required": [
    "name",
    "start",
    "response",
    "max_delay"
  ],
  "additionalProperties": false
}
```

## `$.properties.sequences.items.properties.name`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "声明的唯一标识。使用非保留的英文字母或下划线开头、后接字母数字下划线的名称；不能重复。"
}
```

## `$.properties.sequences.items.properties.start`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "请求开始点规则的id，必须已在rules中声明，不能引用活动规则。"
}
```

## `$.properties.sequences.items.properties.response`

```json
{
  "type": "string",
  "pattern": "^[A-Za-z_][A-Za-z0-9_]*(?![\\s\\S])",
  "not": {
    "enum": [
      "abs",
      "isclose",
      "False",
      "None",
      "True",
      "and",
      "as",
      "assert",
      "async",
      "await",
      "break",
      "class",
      "continue",
      "def",
      "del",
      "elif",
      "else",
      "except",
      "finally",
      "for",
      "from",
      "global",
      "if",
      "import",
      "in",
      "is",
      "lambda",
      "nonlocal",
      "not",
      "or",
      "pass",
      "raise",
      "return",
      "try",
      "while",
      "with",
      "yield"
    ],
    "description": "禁止使用以下保留名称：\"abs\", \"isclose\", \"False\", \"None\", \"True\", \"and\", \"as\", \"assert\", \"async\", \"await\", \"break\", \"class\", \"continue\", \"def\", \"del\", \"elif\", \"else\", \"except\", \"finally\", \"for\", \"from\", \"global\", \"if\", \"import\", \"in\", \"is\", \"lambda\", \"nonlocal\", \"not\", \"or\", \"pass\", \"raise\", \"return\", \"try\", \"while\", \"with\", \"yield\"。"
  },
  "description": "响应点规则的id，必须引用rules中已定义的rising_edge、falling_edge或start_only规则；不能填信号名或sequences中的id。"
}
```

## `$.properties.sequences.items.properties.min_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "允许的最小响应延迟，非负带单位时长，包含端点。"
}
```

## `$.properties.sequences.items.properties.max_delay`

```json
{
  "type": "string",
  "pattern": "^\\s*\\+?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?\\s*(?:ns|us|ms|s)\\s*$",
  "description": "允许的最大响应延迟，不得小于min_delay，包含端点；到期未响应会得到明确配对状态。"
}
```

## `$.properties.sequences.items.properties.max_pending`

```json
{
  "type": "integer",
  "minimum": 1,
  "description": "同时等待响应的请求数上限，正整数，默认65536；不是输入文件总行数。",
  "default": 65536
}
```

## `$.properties.sequences.items.properties.interval`

```json
{
  "description": "此节点采用的间隔来源；省略则继承全局default，多个驱动候选时须明确driver。"
}
```

## `$.properties.sequences.items.properties.interval.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.sequences.items.properties.interval.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"actual\"。"
}
```

## `$.properties.sequences.items.properties.interval.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

## `$.properties.sequences.items.properties.interval.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"fixed\"。"
}
```

## `$.properties.sequences.items.properties.interval.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "fixed计算间隔的带单位正时长，例如100ms；actual/dbc不接受此字段。"
}
```

## `$.properties.sequences.items.properties.interval.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.sequences.items.properties.interval.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.sequences.items.properties.interval.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"dbc\"。"
}
```

## `$.properties.sequences.items.properties.interval.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.intervals`

```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "普通时序计算使用的计时间隔。默认真实记录时间差，可对指定消费者覆盖；不改变信号有效期。",
  "default": {}
}
```

## `$.properties.intervals.properties.default`

```json
{
  "description": "未单独覆盖的消费者采用的计算间隔，省略时为actual真实时间差。"
}
```

## `$.properties.intervals.properties.default.oneOf[0]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.intervals.properties.default.oneOf[0].properties.mode`

```json
{
  "const": "actual",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"actual\"。"
}
```

## `$.properties.intervals.properties.default.oneOf[1]`

```json
{
  "type": "object",
  "required": [
    "mode",
    "value"
  ],
  "additionalProperties": false
}
```

## `$.properties.intervals.properties.default.oneOf[1].properties.mode`

```json
{
  "const": "fixed",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"fixed\"。"
}
```

## `$.properties.intervals.properties.default.oneOf[1].properties.value`

```json
{
  "type": "string",
  "minLength": 2,
  "description": "fixed计算间隔的带单位正时长，例如100ms；actual/dbc不接受此字段。"
}
```

## `$.properties.intervals.properties.default.oneOf[1].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.intervals.properties.default.oneOf[2]`

```json
{
  "type": "object",
  "required": [
    "mode"
  ],
  "additionalProperties": false
}
```

## `$.properties.intervals.properties.default.oneOf[2].properties.mode`

```json
{
  "const": "dbc",
  "description": "间隔来源：actual使用实际记录时间差，fixed使用显式value，dbc在运行时读取驱动报文周期；导出周期对象仅允许dbc。 固定值：\"dbc\"。"
}
```

## `$.properties.intervals.properties.default.oneOf[2].properties.driver`

```json
{
  "type": "string",
  "minLength": 1,
  "description": "明确推进此计算或DBC周期选择的原信号名；仅在唯一可判断的声明中允许省略。"
}
```

## `$.properties.diagnostics`

```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "按需开启额外追溯、完整性检查或现场保留。三项独立，默认均关闭。",
  "default": {}
}
```

## `$.properties.diagnostics.properties.trace`

```json
{
  "type": "boolean",
  "default": false,
  "description": "是否生成额外详细追溯，默认false；关闭时仍保留必要结果和错误处理。"
}
```

## `$.properties.diagnostics.properties.integrity`

```json
{
  "type": "boolean",
  "default": false,
  "description": "是否执行额外完整性诊断，默认false；不取消普通分析所必需的输入检查。"
}
```

## `$.properties.diagnostics.properties.retain_work`

```json
{
  "type": "boolean",
  "default": false,
  "description": "是否保留本次自有工作现场，默认false；不授权删除或保留无关用户文件。"
}
```

## `$.properties.imports`

```json
{
  "type": "array",
  "description": "可选公共定义文件，按列表顺序导入sources/signals/derived，再追加本文件声明；重名报错，仅允许一层。省略或空数组表示没有外部定义。"
}
```

## `$.properties.imports.items`

```json
{
  "type": "string",
  "minLength": 1,
  "pattern": "^(?!.*://)(?!.*[\\*?\\[\\]])[\\s\\S]+$",
  "description": "明确的本地.json/.yaml/.yml文件路径；相对主配置目录解释，不支持URL或通配符。"
}
```

## `$.properties.overrides`

```json
{
  "type": "object",
  "additionalProperties": false,
  "description": "公共定义的显式局部覆盖；必须同时声明imports，未知目标与不允许字段会报错。"
}
```

## `$.properties.overrides.properties.sources`

```json
{
  "type": "object",
  "additionalProperties": {
    "type": "object"
  },
  "description": "按已有定义名称填写允许覆盖的字段；不能新增目标、改名或覆盖自由元数据。"
}
```

## `$.properties.overrides.properties.signals`

```json
{
  "type": "object",
  "additionalProperties": {
    "type": "object"
  },
  "description": "按已有定义名称填写允许覆盖的字段；不能新增目标、改名或覆盖自由元数据。"
}
```

## `$.properties.overrides.properties.derived`

```json
{
  "type": "object",
  "additionalProperties": {
    "type": "object"
  },
  "description": "按已有定义名称填写允许覆盖的字段；不能新增目标、改名或覆盖自由元数据。"
}
```
