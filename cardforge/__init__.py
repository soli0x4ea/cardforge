# -*- coding: utf-8 -*-
"""CardForge — DLC 数字生命卡片编译器。

CardForge 是 DLC 生态的编译器。它把各种形式的创意输入
（设计文档 / 聊天记录 / 小说 / 一句话）编译成可运行的数字生命卡片。

核心管线：
    输入 → 解析器(DesignIR) → 生成器(DLC JSON) → 校验器 → 测试器 → 可运行卡片
"""

from .design_ir import DesignIR, Complexity, Archetype
from .forge import (
    forge_from_design,
    forge_from_one_liner,
    _complete_forge,
)

__all__ = [
    "DesignIR",
    "Complexity",
    "Archetype",
    "forge_from_design",
    "forge_from_one_liner",
]
__version__ = "1.0.8"
