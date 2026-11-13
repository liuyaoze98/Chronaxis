"""核对标量类拆分后的运行时注解、公开身份和进程传输。

旧 pickle 样例由拆分前的 ScalarValue 生成，保留枚举标签无效但原码有效的
情况。冷进程只检查源码导入顺序，不把源码路径注入当作安装包验收。
"""

import base64
from concurrent.futures import ProcessPoolExecutor
import importlib
import json
import multiprocessing
from pathlib import Path
import pickle
import subprocess
import sys
from typing import get_type_hints
import unittest

from chronaxis.core import ScalarValue
from chronaxis.core.models import SignalSample, SourceRef
from chronaxis.core.types import QualityFlag as Q, SignalDType as D


# 拆分前的公开路径与字段布局；来源为基线 51bad3c3 的真实 protocol=4 输出。
_OLD_ENUM_PICKLE = (
    "gASV+AAAAAAAAACMFmNocm9uYXhpcy5jb3JlLm51bWVyaWOUjAtTY2FsYXJWYWx1ZZSTlCmB"
    "lH2UKIwFdmFsdWWUSyGMBWR0eXBllIwUY2hyb25heGlzLmNvcmUudHlwZXOUjAtTaWduYWxE"
    "VHlwZZSTlIwEZW51bZSFlFKUjAV2YWxpZJSJjAdxdWFsaXR5lGgHjAtRdWFsaXR5RmxhZ5ST"
    "lEsQhZRSlIwGbGFiZWxzlIwCT26UhZSMBGNvZGWUaAIpgZR9lChoBUshaAZoCYwGdWludDY0"
    "lIWUUpRoDYhoDmgQSwCFlFKUaBMpaBZOjAdwYXJ0aWFslIl1YmgeiXViLg=="
)


def _round_trip_in_spawn(sample, scalar):
    """在新进程核对类型身份，再把实际对象返回父进程。

    参数: sample 为带枚举原码的样本，scalar 为标签及原码质量不同的标量。
    返回: 原样本、原标量和三个身份判断。
    异常: 导入或注解解析失败直接传回父进程，不忽略序列化错误。
    """
    from chronaxis.core.numeric import ScalarValue as public_scalar
    from chronaxis.core.scalar import ScalarValue as shared_scalar

    checks = (
        public_scalar is shared_scalar is ScalarValue,
        type(sample.code) is public_scalar,
        get_type_hints(SignalSample)["code"] == public_scalar | None,
    )
    return sample, scalar, checks


class ScalarValueContractTests(unittest.TestCase):
    """通过冷导入、反射和实际 spawn 检查拆分不改变公开对象。"""

    def test_annotations_resolve_to_the_public_class(self):
        """模型及标量自身的原码注解均解析到同一个公开类。

        参数: 无。返回: None。异常: 注解无法解析或公开类身份改变时失败。
        """
        self.assertEqual(get_type_hints(SignalSample)["code"], ScalarValue | None)
        self.assertEqual(get_type_hints(ScalarValue)["code"], ScalarValue | None)
        self.assertIs(importlib.import_module("chronaxis.core.numeric").ScalarValue, ScalarValue)
        self.assertIs(importlib.import_module("chronaxis.core.scalar").ScalarValue, ScalarValue)
        self.assertEqual(ScalarValue.__module__, "chronaxis.core.numeric")

    def test_cold_import_orders_resolve_annotations(self):
        """每种入口在全新进程先导入，均无循环依赖或第三方依赖加载。

        参数: 无。返回: None。异常: 冷进程超时、导入失败或断言不符时失败。
        """
        modules = (
            "chronaxis.core.models", "chronaxis.core.numeric",
            "chronaxis.core.scalar", "chronaxis.core",
        )
        source = str(Path(__file__).resolve().parents[2] / "src")
        code = """
import importlib, json, sys
from typing import get_type_hints
sys.path.insert(0, sys.argv[1])
for name in json.loads(sys.argv[2]):
    importlib.import_module(name)
from chronaxis.core import ScalarValue
from chronaxis.core.models import SignalSample
from chronaxis.core.numeric import ScalarValue as numeric_scalar
from chronaxis.core.scalar import ScalarValue as shared_scalar
assert ScalarValue is numeric_scalar is shared_scalar
assert get_type_hints(SignalSample)['code'] == ScalarValue | None
assert get_type_hints(ScalarValue)['code'] == ScalarValue | None
assert not {'numpy', 'can', 'cantools'} & set(sys.modules)
print('ok')
"""
        for index in range(len(modules)):
            order = modules[index:] + modules[:index]
            with self.subTest(first=order[0]):
                result = subprocess.run(
                    [sys.executable, "-X", "utf8", "-B", "-I", "-S", "-c", code,
                     source, json.dumps(order)],
                    capture_output=True, text=True, encoding="utf-8", timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.strip(), "ok")

    def test_existing_pickle_and_new_payload_keep_the_public_path(self):
        """拆分前的 pickle 可读取，新对象仍使用完全相同的公开路径和布局。

        参数: 无。返回: None。异常: 序列化失败或路径、字段内容变化时失败。
        """
        payload = base64.b64decode(_OLD_ENUM_PICKLE)
        expected = ScalarValue(33, D.ENUM, False, Q.OUT_OF_RANGE, ("On",),
                               ScalarValue(33, D.UINT64))
        restored = pickle.loads(payload)
        self.assertIs(type(restored), ScalarValue)
        self.assertIs(type(restored.code), ScalarValue)
        self.assertEqual(restored, expected)
        self.assertEqual(pickle.dumps(expected, protocol=4), payload)
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            with self.subTest(protocol=protocol):
                value = pickle.loads(pickle.dumps(expected, protocol=protocol))
                self.assertIs(type(value), ScalarValue)
                self.assertEqual(value, expected)

    def test_spawn_preserves_enum_code_and_independent_quality(self):
        """跨进程往返保留无标签原码、独立质量原因和无符号整数端点。

        参数: 无。返回: None。异常: 进程启动失败、超时或往返内容不一致时失败。
        """
        code = ScalarValue(2 ** 64 - 1, D.UINT64)
        sample = SignalSample("mode", 10, None, False, Q.OUT_OF_RANGE,
                              SourceRef("session", "sensor", "mode"), 0, code)
        scalar = ScalarValue("On", D.ENUM, labels=("On",),
                             code=ScalarValue(None, D.UINT64, False, Q.MISSING))
        with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
            restored_sample, restored_scalar, checks = pool.submit(
                _round_trip_in_spawn, sample, scalar,
            ).result(timeout=30)
        self.assertEqual(checks, (True, True, True))
        self.assertEqual(restored_sample, sample)
        self.assertEqual(restored_scalar, scalar)
        self.assertIs(type(restored_sample.code), ScalarValue)
        self.assertIs(type(restored_scalar.code), ScalarValue)
        self.assertEqual(restored_sample.quality, Q.OUT_OF_RANGE)
        self.assertEqual(restored_sample.code.quality, Q.NONE)
        self.assertEqual(restored_scalar.quality, Q.NONE)
        self.assertEqual(restored_scalar.code.quality, Q.MISSING)
